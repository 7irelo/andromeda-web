# Andromeda AI service

An internal FastAPI service that owns every model call. Django talks to it
over the private Docker network; browsers never reach it, and it's the only
container that holds model-provider keys.

## Endpoints

| Route | Purpose |
|---|---|
| `POST /v1/moderate` | Classify a post, comment or listing as `allow`, `review` or `remove` |
| `POST /v1/catchup` | Summarise chat messages with verified message citations |
| `POST /v1/video/chapters` | Chapter a video from its timed transcript; starts and titles are checked deterministically |
| `POST /v1/replies` | Three short smart-reply suggestions for a chat; `variant` (`haiku` / `luna` / `lora`) picks the primary route |
| `POST /v1/compose` | "Help me write": rewrite a draft in a tone, fix grammar, shorten or translate (en, zu, af, st, xh) |
| `GET /healthz`, `GET /metrics` | Liveness and Prometheus metrics (tokens, cost, latency, fallbacks) |

## How it works

- **Gateway** ([`app/gateway.py`](app/gateway.py)): per-job routes with a
  primary model and a cross-provider fallback, plus per-provider circuit
  breakers, per-user daily token budgets, and token and cost metering.
- **Moderation** is a deterministic workflow:
  1. OpenAI `omni-moderation-latest` gives a free generic signal.
  2. Claude Haiku 5.5 applies Andromeda's policy rubric through structured
     output.
  3. Claude Sonnet 5.5 is called only when Haiku is unsure or the stages
     disagree.
  4. If every model is down, the service fails closed for new accounts
     (review) and open for established ones (allow).
- **Catch me up** uses Claude Haiku 5.5 with prompt caching on the stable
  system prompt. Every claim must cite message ids; invented ids are
  dropped, and claims left uncited are removed.

| Job | Primary | Fallback |
|---|---|---|
| `moderation.classify` | `claude-haiku-5-5` | `gpt-6-luna` |
| `moderation.escalate` | `claude-sonnet-5-5` | `gpt-6.1-terra` |
| `catchup.summarise` | `claude-haiku-5-5` | `gpt-6.1-terra` |
| `replies.suggest` (A/B `haiku`) | `claude-haiku-5-5`, effort low, 256 tokens | `gpt-6-luna` |
| `replies.suggest.luna` (A/B `luna`) | `gpt-6-luna` | `claude-haiku-5-5` |
| `replies.suggest.lora` (A/B `lora`) | self-hosted LoRA on vLLM (only when `VLLM_BASE_URL` is set) | `claude-haiku-5-5`, `gpt-6-luna` |
| `compose.rewrite` | `claude-haiku-5-5` | `gpt-6-luna` |

## Security

- **Caller authentication:** each request carries an HS256 service token
  minted by Django (audience- and issuer-bound, 60-second lifetime, unique
  `jti`). The acting user comes only from the token, never from the request
  body.
- **Untrusted input:** user content is wrapped in `<untrusted>` blocks, and
  any attempt to forge the delimiter is neutralised. The system prompt tells
  the model never to follow instructions found inside them.
- **Untrusted output:** model output passes through the same distrust. Links
  that weren't in the source content are stripped.
- **No provider retention:** OpenAI calls set `store=False`. No interactive
  API docs are served.
- **Container hardening:** the container runs as non-root on a read-only
  filesystem, with all capabilities dropped and `no-new-privileges`.

- **Smart replies** keep the prompt short (latency goal < 400 ms p95) and
  treat the output as untrusted: at most three, 120 characters each,
  duplicates dropped, and any suggestion with a link, phone number or email
  that wasn't in the chat is dropped. With moderation configured, flagged
  suggestions are dropped, and if moderation is unreachable none are shown.
- **Compose assist** caps the rewrite's length relative to the draft and
  strips contact details the author didn't write.
- **Fine-tuning (v2, offline)** lives in [`finetune/`](finetune/serve.md):
  SFT and DPO datasets built from pseudonymised seed conversations only, a
  LoRA/QLoRA training script, and how to serve the adapter on vLLM.

## Development

```bash
cd ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest            # fake providers: no keys, no network
ruff check .
```

## Evals

```bash
python -m evals.run_replies --a haiku --b luna   # smart replies: cross-family judged win rate + safety
```


```bash
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=...
python -m evals.run_moderation --gate 0.65
```

The golden set ([`evals/datasets/moderation_v1.jsonl`](evals/datasets/moderation_v1.jsonl))
has 35 synthetic items. It covers clean posts, hard negatives (profanity,
reclaimed language, news), scams, illegal goods, threats in English and
isiZulu, hate speech, doxxing, borderline cases and embedded
prompt-injection attempts.

Baseline (2026-10-27):

| Metric | Value |
|---|---|
| Accuracy | 0.857 |
| Macro-F1 | 0.709 (allow 0.87 · review 0.29 · remove 0.97) |
| Severe misses (harmful content allowed) | 0 |
| False removals | 0 |
| Prompt-injection items handled correctly | 2 / 2 |
| Escalation rate to Sonnet | 5.7% |
| Cost | $0.32 per 1,000 items |
| Latency | p50 2.0 s · p95 4.4 s |

The `review` class is the weak spot: borderline protest language and vague
digs are mostly allowed. That's the next thing to improve, through rubric
examples, then distillation onto a calibrated classifier.
