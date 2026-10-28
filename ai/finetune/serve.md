# Serving the smart-reply LoRA on vLLM

The v2 smart-reply model is a LoRA adapter on a small open model
(see [`train_lora.py`](train_lora.py)). It's served by vLLM's
OpenAI-compatible server, and the gateway reaches it through the optional
`VLLMProvider` in [`app/providers.py`](../app/providers.py). Nothing here
is needed to run Andromeda: without `VLLM_BASE_URL`, the `lora` variant
falls through to Claude Haiku and then GPT-6 Luna.

## Pipeline

```bash
# 1. Django: synthetic conversations among seed accounts only, pseudonymised
python manage.py export_reply_sft --out conversations.jsonl
#    (set REPLY_SFT_CAPTURE_SEED_TEXT=True while generating synthetic traffic
#     if you want suggestion text for preference pairs; real users' text is never stored)

# 2. ai/: build the datasets
python -m finetune.build_sft --in conversations.jsonl --out sft.jsonl
python -m finetune.build_dpo --in conversations.jsonl --out dpo.jsonl

# 3. GPU box: train (see the hyperparameters in train_lora.py)
pip install -r finetune/requirements.txt
python -m finetune.train_lora --data sft.jsonl --dpo dpo.jsonl --out adapters/replies-v2

# 4. Offline eval against the hosted variants before any traffic moves
python -m evals.run_replies --a lora --b haiku
```

## vLLM with multi-LoRA

One base model serves many adapters, each addressed by name in the
request's `model` field. The gateway route is
`Route('vllm', 'andromeda-replies-lora', ...)`, so register the adapter
under that name:

```bash
vllm serve Qwen/Qwen2.5-3B-Instruct \
  --revision <pinned-commit> \
  --load-format safetensors \
  --enable-lora \
  --lora-modules andromeda-replies-lora=/adapters/replies-v2-dpo \
  --max-loras 4 --max-lora-rank 16 \
  --max-model-len 4096 \
  --guided-decoding-backend xgrammar \
  --api-key "$VLLM_API_KEY" \
  --host 0.0.0.0 --port 8000
```

- `--load-format safetensors` refuses pickle-based weights, and
  `--trust-remote-code` is deliberately not passed.
- `--max-loras` is how many adapters stay resident on the GPU at once. New
  adapter versions (`andromeda-replies-lora-v3`, a per-language adapter, ...)
  can be added at start-up with more `--lora-modules` entries, or at runtime
  with `VLLM_ALLOW_RUNTIME_LORA_UPDATING=True` and
  `POST /v1/load_lora_adapter`. Keep that endpoint off in production unless
  it's behind the API key and the private network.
- Structured output uses `response_format: {"type": "json_schema", ...}`,
  which vLLM enforces with guided decoding (xgrammar). The provider still
  validates the JSON and treats anything malformed as a transient failure,
  so the gateway falls back to the hosted models.
- Prefix caching (on by default in recent vLLM) caches the stable system
  prompt, like `cache_control` does for Anthropic.

Latency: a 3B model in bf16 on one L4 produces the ~60 tokens of three short
replies in well under 400 ms at low concurrency. Watch
`ai_latency_seconds{job="replies.suggest.lora"}` in Grafana.

## Wiring it into the gateway

1. Run vLLM on the private Docker network only (never published), e.g. a
   `vllm` service with a GPU reservation, no `ports:`, and an API key.
2. Configure the AI service:

   ```bash
   VLLM_BASE_URL=http://vllm:8000/v1   # OpenAI convention: include /v1
   VLLM_API_KEY=...                     # same value as vLLM's --api-key
   ```

   `build_gateway()` in `app/main.py` then registers a `VLLMProvider` under
   the provider name `vllm`. Without `VLLM_BASE_URL` no provider is
   registered, and routes that name it are skipped.
3. The job `replies.suggest.lora` routes vLLM first, then Claude Haiku, then
   GPT-6 Luna. The `variant` field of `/v1/replies` is checked against an
   allow-list (`haiku`, `luna`, `lora`) and only selects the job.
4. Move traffic in Django with the sticky bucketing helper. The variant
   weights are read from `SMART_REPLY_VARIANTS` (default
   `{'haiku': 50, 'luna': 50}`); add it to `settings.py`, e.g.

   ```python
   SMART_REPLY_VARIANTS = {'haiku': 45, 'luna': 45, 'lora': 10}
   ```

   Append new variants at the end and grow them gradually: buckets are
   assigned in order, so users only ever move *into* a growing variant.
5. Compare acceptance with `python manage.py reply_metrics` and the offline
   win rate with `python -m evals.run_replies`.

### How `VLLMProvider` behaves

| vLLM response | Gateway sees |
|---|---|
| 200 with valid JSON matching the schema | result, metered (cost 0: GPU time isn't per token) |
| 200 but invalid JSON / schema mismatch / `finish_reason: length` | `ProviderError` → next route |
| 404 (adapter not loaded), 408, 429, 5xx, timeouts, connection errors | `ProviderError` → next route; the circuit breaker opens after 5 |
| other 4xx | a bad request: raised, not retried elsewhere |
| image input | `ProviderError` (text-only) → next route |
