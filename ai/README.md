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
python -m evals.run_moderation --dataset moderation_v2.jsonl --gate 0.90
python -m evals.run_moderation --dataset moderation_holdout_v1.jsonl --gate 0.85
```

Two synthetic sets, both covering clean posts, hard negatives (profanity, figures of speech, sports talk,
news, helplines), scams, illegal goods, threats, hate speech, doxxing, self-harm signals, borderline cases
and prompt-injection attempts, in English, isiZulu and Afrikaans:

- [`moderation_v2.jsonl`](evals/datasets/moderation_v2.jsonl) (60 items) is the **dev set** the policy is
  tuned against.
- [`moderation_holdout_v1.jsonl`](evals/datasets/moderation_holdout_v1.jsonl) (24 items) was written
  *after* the policy change and is never used for tuning. Its numbers are the honest ones.

Policy v1 → v2 (2026-10-28). v2 spells out what counts as borderline (veiled threats, put-downs without
slurs, fraud signals in listings, self-harm signals), and lets a confident escalation overrule a stage-0
flag on harmless text such as news headlines.

| Held-out set | Policy v1 | Policy v2 |
|---|---|---|
| Macro-F1 | 0.831 | **0.948** |
| Review recall | 0.75 | **0.92** |
| Allow F1 | 0.88 | 1.00 |
| Remove F1 | 0.80 | 0.89 |
| Severe misses (harmful content allowed) | 0 | 0 |
| False removals | 0 | 0 |

On the dev set v2 scores macro-F1 0.965 (v1: 0.863). Cost is about $0.8 per 1,000 items, with an escalation
rate of about 18% and p95 latency of 4–5 s. The remaining errors are judgement calls between review and
remove (an offer asking for ID and bank details was removed rather than reviewed).

The first baseline (35 items, 2026-10-27) reported review F1 0.29. It had only four review items, so that
figure was mostly small-sample noise; the larger sets above replace it.

### Distilled first pass (optional, off by default)

[`distill/`](distill/) trains a small classifier from a frontier teacher: 636 synthetic posts
([`generate.py`](distill/generate.py)) labelled by Claude Opus through the Batch API
([`label.py`](distill/label.py), about $2.08), then text-embedding-3-small vectors into a
temperature-calibrated logistic regression ([`train.py`](distill/train.py)). The model is plain JSON:
coefficients and a threshold, nothing that executes on load. The student may only answer "allow", and only
above a threshold chosen so that at most 1% of the validation items it waves through were review or remove.
Everything else still goes through the LLM pipeline. It is scored on the human-labelled sets, never on its
own training data.

| | Frontier pipeline (v2) | Distilled student |
|---|---|---|
| Held-out macro-F1 | **0.948** | 0.616 |
| Dev macro-F1 | **0.965** | 0.744 |
| Traffic it decides alone (dev / held-out) | n/a | 30% / 21% |
| Non-allow items waved through (dev / held-out) | 0 / 0 | 1 / 1 |
| Cost per 1,000 items | ~$0.8 | ~$0.001 |
| Latency per item | 4–5 s p95 | ~20–40 ms |

The two items it let through were borderline "review" cases, a veiled threat about shutting a town down and
a put-down aimed at a group, not severe harm. That still misses the bar, so the stage stays off.
`MODERATION_STUDENT_PATH` turns it on once a retrained student meets that bar on the held-out set. More teacher
labels on borderline content are the obvious next step.
