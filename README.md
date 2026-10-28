# Andromeda

> A full-stack social platform: feed, real-time chat, groups, marketplace,
> video and pages. Django, Angular, PostgreSQL with pgvector, a Neo4j social
> graph and an event-driven Celery backbone, with authorization and privacy
> enforced on every request. An internal AI service (Claude and OpenAI, with
> Deepgram for speech) adds moderation, hybrid semantic search with grounded
> answers, chat summaries, smart replies, captions, an approval-gated
> assistant with an MCP endpoint, and a LightGBM feed ranker, each with its
> own eval.

[![CI](https://github.com/7irelo/andromeda-web/actions/workflows/ci.yml/badge.svg)](https://github.com/7irelo/andromeda-web/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-5.2_LTS-green.svg)](https://djangoproject.com/)
[![Angular](https://img.shields.io/badge/angular-22-red.svg)](https://angular.dev/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

![Andromeda: feed, chat, marketplace, profile, API, monitoring](docs/screenshots/andromeda-ui.png)

---

## Contents

- [Features](#features)
- [Security model](#security-model)
- [AI features](#ai-features)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Quick start (Docker)](#quick-start-docker)
- [Local development](#local-development)
- [Testing & CI](#testing--ci)
- [Monitoring](#monitoring)
- [Project structure](#project-structure)
- [Contributing](#contributing)

---

## Features

| Area | What you can do |
|---|---|
| **Accounts** | Register (terms accepted and recorded), email verification, sign in with optional TOTP two-factor, a list of signed-in devices you can revoke one by one, password change and reset |
| **Feed & posts** | Text/image/video posts, public / friends / only-me audiences, six reactions, threaded comments, sharing, #hashtags, @mentions, link previews, a ranked feed with "Why am I seeing this?" |
| **Friends** | Requests (send, accept, decline, cancel), unfriend, friends lists, blocking, suggestions from the Neo4j graph |
| **Privacy** | Per-user controls over profile, friends list, online status, messaging, friend requests and search. One switch turns every AI feature off and keeps your content away from models. Download all your data as a zip; account deletion has a 14-day grace period, then erases content and media |
| **Chat** | Real-time DMs and group chats over WebSockets, typing indicators, read receipts, presence, private attachments, voice notes with transcripts, group admin tools |
| **Notifications** | Real-time in-app, Web Push (VAPID) and email digests, per-category preferences, grouped "Thandi and 3 others liked your post" |
| **Groups** | Public, private and secret groups, a group feed, join requests with an admin approval queue, admin/moderator roles, invites |
| **Marketplace** | Listings with image galleries, categories, price filters, saved items, reviews, Message Seller, mark sold / relist, an AI listing draft from your photos |
| **Watch** | Video upload, HLS adaptive streaming, captions and chapters, likes, comments, one view counted per viewer |
| **Pages** | Business and community pages, follow/unfollow, posting as a page for its admins and editors |
| **Search** | People, posts, groups, pages, listings and videos. Hybrid lexical + vector retrieval, and "Ask Andromeda" answers questions from what you're allowed to see, with citations |
| **Trust & safety** | Report anything, a staff moderation console, warnings, suspensions and bans, appeals, "My decisions" for authors |
| **App** | Installable PWA, works offline for the app shell |
| **Operations** | Prometheus metrics (including Celery and model drift), Grafana dashboards, OpenAPI docs, a demo-data seeder |

---

## Security model

Security is a first-class feature, and the regression suite in
[`server/core/test_security.py`](server/core/test_security.py) locks it in.

**Authorization**
- Every endpoint is authenticated by default. Object-level permissions mean
  only owners (or group and page admins) can edit or delete content.
- One visibility service ([`core/visibility.py`](server/core/visibility.py))
  decides what each user may see. It applies post audience, friendship,
  group privacy and two-way blocking, and every list, detail, search and
  notification path goes through it.
- Chat rooms and messages are visible only to members. Attachments are
  streamed through an authenticated endpoint, never a public URL.
- Other users never receive your email, birth date or privacy settings.

**Sessions**
- Access tokens last 15 minutes, live only in browser memory and carry no
  personal data. Optional TOTP two-factor; the secret is encrypted at rest.
- Each sign-in is a device session you can see and revoke. Suspended
  accounts and accounts pending deletion are refused on every request.
- Refresh tokens are `HttpOnly`, `Secure`, `SameSite=Strict` cookies scoped
  to `/api/auth/`. They rotate on every use and are blacklisted afterwards.
- Changing or resetting the password revokes every session. Password reset
  responses don't reveal whether an account exists.
- WebSockets authenticate with single-use, 30-second tickets, so no token
  ever appears in a URL or a log.

**Input & uploads**
- Uploads are identified by their content, not their filename. Images are
  re-encoded, which strips EXIF and GPS metadata and refuses decompression
  bombs. Executables and active content are rejected, and stored filenames
  are random.
- Link previews are SSRF-safe: public IPs only, the resolved IP is pinned
  against DNS rebinding, every redirect is re-validated, and size and time
  are capped.
- Throttling applies to anonymous traffic, per-user traffic, writes and the
  auth endpoints. WebSocket frames are rate-limited and size-capped.

**Platform**
- The app refuses to start without a strong `SECRET_KEY` when `DEBUG` is off.
- Secure cookies, HSTS (configurable), and a strict CSP and security headers
  are served from nginx.
- Only the web app's port is published. Databases, brokers and dashboards
  bind to `127.0.0.1`, Flower requires a password, and containers run as
  non-root.
- CI runs bandit-style lint rules, `pip-audit`, `npm audit`, gitleaks,
  Trivy and Django's deploy checks on every push.

Found a vulnerability? Please open a private security advisory on GitHub
rather than a public issue.

---

## AI features

All model calls go through an internal FastAPI service ([`ai/`](ai/README.md)).
It is the only component holding provider keys, and Django calls it with
60-second signed service tokens. Django decides what each user may see; the
AI service never touches the database and only receives content the
requesting user is already allowed to read. Members who turn AI off are never
sent to a model, as authors or as readers.

Models are chosen per job, with a cross-provider fallback for each:

| Feature | Models | How it works |
|---|---|---|
| **Moderation** | OpenAI omni-moderation → Claude Haiku 5.5 → Sonnet 5.5 | Free generic screen first, then Haiku applies the community policy, and Sonnet is called only when Haiku is unsure. Clear violations are hidden (the author is notified and can appeal); borderline cases go to the staff console. |
| **Semantic search** | text-embedding-3-small, pgvector | Full-text and vector results fused with reciprocal rank fusion, scoped by visibility inside the SQL query. Optional query rewrite and rerank. |
| **Ask Andromeda** | Claude Sonnet 5.5 | Grounded answers over retrieved content. Every claim must cite a source id that was actually provided; uncited claims are dropped and it abstains when the sources don't answer. Sources that look like prompt injection are dropped and PII is redacted. |
| **Catch me up** | Claude Haiku 5.5 | Summarises what you missed in a chat: topics, decisions and questions for you, each citing real message ids. |
| **Smart replies** | Claude Haiku 5.5 vs gpt-6-luna (A/B) | Three reply chips above the composer; tapping fills the input, never sends. Only a keyed hash of each suggestion is logged, for acceptance metrics. |
| **Help me write** | Claude Haiku 5.5 | Rewrite a draft to be friendlier, more formal or shorter, fix grammar, or translate into English, isiZulu, Afrikaans, Sesotho or isiXhosa. You accept or discard. |
| **Listing assistant** | Claude Sonnet 5.5 (vision) | Drafts a title, description, category and condition from your photos. |
| **Voice & video** | Deepgram Nova-3 / Aura-2 | Voice-note transcripts, video captions (WebVTT) and AI chapters. |
| **Assistant** | Haiku router, Opus 5.5 planner, Sonnet 5.5 | Searches, summarises and drafts. Tools run in Django as you; posting or sending always becomes a confirmation card you approve. Runs are durable (append-only steps on a dedicated queue) and every AI-initiated write is audited. The same tools are exposed over MCP with scoped, revocable personal access tokens. See [ADR 0001](docs/ai/adr/0001-durable-assistant-runs.md) and [MCP security](docs/ai/mcp-security.md). |
| **Feed ranking** | LightGBM | 17 point-in-time features, calibrated engagement probability, a sticky A/B test against the heuristic ranker with a kill switch, and PSI drift alerts. |

**Guardrails:** per-user daily token and audio budgets, circuit breakers,
untrusted-content delimiting, link and contact stripping, PII redaction,
injection screening and graceful degradation when a provider is down.

**Measured, not assumed** (details and methods in [`ai/README.md`](ai/README.md)):

| Eval | Result |
|---|---|
| Moderation, held-out set (24 items, never tuned on) | macro-F1 **0.948**, review recall 0.92, 0 severe misses, 0 false removals, ~$0.8 per 1,000 items |
| Retrieval, 30 golden queries | recall@10: lexical 0.10 → hybrid **0.968** (p50 0.38 s); 0 visibility leaks |
| Distilled moderation student (Opus-labelled) | decides 21–30% of traffic alone at ~$0.001 per 1,000 items, but let one borderline item through per set, so it ships **off** |
| Feed ranker (synthetic engagement only) | AUC 0.705 vs 0.629 for the heuristic, ECE 0.010 |

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Angular 22 (standalone components), Angular Material, RxJS, TypeScript 6 |
| API | Django 5.2 LTS, Django REST Framework, SimpleJWT, drf-spectacular |
| Real-time | Django Channels over Redis (chat, notifications, presence) |
| Relational DB | PostgreSQL 15 with pgvector (source of truth, full-text and vector search) |
| Social graph | Neo4j 5 (friend-of-friend suggestions, mutual friends) |
| Async work | Celery 5.5 + RabbitMQ 3 (`notifications`, `messages`, `emails`, `video`, `ai`, `default` queues), Celery Beat, Flower |
| Cache | Redis 7 |
| Media | MinIO (S3-compatible), split into public and private prefixes |
| Observability | Prometheus, Grafana, Redis, Postgres and Celery exporters |
| AI | FastAPI, Pydantic, Anthropic (Claude Haiku / Sonnet / Opus 5.5) and OpenAI SDKs, Deepgram, LightGBM, scikit-learn |
| Delivery | Docker Compose, nginx, GitHub Actions |

---

## Architecture

```
                     ┌─────────────────────────────────────────────┐
  Browser ─ HTTPS ─► │ nginx  (Angular build, CSP, /media/public/) │
  (Angular)          └──────────────┬──────────────────────────────┘
     │  WebSocket /ws (ticket auth)  │ /api
     └────────────────────►  Django 5.2 (DRF + Channels, ASGI)
                              │         │          │
                              ▼         ▼          ▼
                         PostgreSQL  Redis      MinIO
                         (truth)   (cache, WS)  (media)
                              │
                       on commit │
                              ▼
                RabbitMQ ──► Celery workers ──► Neo4j (graph read model)
                (notifications · messages · emails · video · ai · default)
                                  │
                   signed service token (60 s)
                                  ▼
                   AI service (FastAPI) ──► Anthropic · OpenAI · Deepgram

  Prometheus ◄── /metrics + exporters (internal only) ──► Grafana
```

- **Writes** go to Postgres. Graph projections and side effects are queued
  only after the transaction commits, as idempotent, retried Celery tasks,
  so a Neo4j or broker outage never fails a request.
- **Real-time** events go through Celery to the Channels layer and out to
  each user's notification socket or chat room.
- **Reads** pass through the visibility service before serialization.

---

## Quick start (Docker)

**Requirements:** Docker Desktop ≥ 24.

```bash
cp .env.example .env
# Required: set SECRET_KEY, FLOWER_PASSWORD and AI_SERVICE_SECRET, and change every *_PASSWORD.
# Optional: ANTHROPIC_API_KEY, OPENAI_API_KEY and DEEPGRAM_API_KEY enable the AI features.
python -c "import secrets; print(secrets.token_urlsafe(64))"   # use as SECRET_KEY
docker compose up --build
```

Migrations run on start-up. Then create an admin account and, optionally,
demo data:

```bash
docker compose exec django python manage.py createsuperuser
docker compose exec django python manage.py seed --users 200 --i-know-this-is-not-production
```

| Service | URL | Notes |
|---|---|---|
| **App** | http://localhost:4200 | register, or sign in as a seeded `demo0` user |
| API docs | http://localhost:8000/api/docs/ | staff accounts only when `DEBUG` is off |
| Django admin | http://localhost:8000/admin/ | path set by `ADMIN_URL` |
| Grafana | http://localhost:3000 | `GRAFANA_USER` / `GRAFANA_PASSWORD` |
| Prometheus | http://localhost:9090 | |
| RabbitMQ | http://localhost:15672 | `RABBITMQ_USER` / `RABBITMQ_PASSWORD` |
| Flower | http://localhost:5555 | `FLOWER_USER` / `FLOWER_PASSWORD` |
| Neo4j Browser | http://localhost:7474 | `neo4j` / `NEO4J_PASSWORD` |

Everything except the app is bound to `127.0.0.1`. Behind TLS in
production, also set `SECURE_SSL_REDIRECT=True` and `SECURE_HSTS_SECONDS`.

```bash
docker compose down        # stop, keep data
docker compose down -v     # stop and wipe all volumes
```

---

## Local development

Run the infrastructure in Docker and the app processes natively, with hot
reload:

```bash
bash dev.sh        # macOS / Linux / Git Bash   flags: --no-client --no-celery --reset-db
.\dev.ps1          # Windows PowerShell         flags: -NoClient -NoCelery -ResetDb
```

<details>
<summary>Manual setup</summary>

**Backend**

```bash
docker compose up -d postgres redis rabbitmq neo4j minio

cd server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

export DEBUG=True POSTGRES_HOST=localhost
export REDIS_URL=redis://:redis_secret@localhost:6379/0
export RABBITMQ_URL=amqp://andromeda:andromeda_secret@localhost:5672/andromeda
export NEO4J_BOLT_URL=bolt://neo4j:andromeda_secret@localhost:7687

python manage.py migrate
python manage.py seed --users 100
python manage.py runserver
celery -A andromeda worker -l info -Q notifications,messages,emails,default,video,ai   # separate terminal; video needs ffmpeg
```

**Frontend**

```bash
cd client
npm ci --legacy-peer-deps
npm start      # http://localhost:4200, proxies /api and /ws to :8000
```

</details>

---

## Testing & CI

```bash
cd server
pytest                                          # in-memory SQLite, no services needed
pytest --cov=. --cov-report=term-missing        # coverage (CI gate: 70%)
ruff check .                                    # pyflakes + bandit security rules

cd ../client
npm run test:ci                                 # Karma, headless Chrome
```

The GitHub Actions pipeline ([`ci.yml`](.github/workflows/ci.yml)) runs on
every push and pull request:

| Job | Checks |
|---|---|
| Backend | ruff, migration drift, migrations applied on PostgreSQL, `check --deploy`, pytest with a coverage gate |
| Frontend | unit tests, production build |
| AI service | ruff, unit tests with fake providers (live evals run on demand in `ai-evals.yml`) |
| Dependency audit | `pip-audit`, `npm audit` |
| Secret scan | gitleaks over the full history |
| Docker | compose validation, image builds, Trivy vulnerability scan |

---

## Monitoring

Grafana ships with the **Andromeda Overview** dashboard:

| Panel | Metric |
|---|---|
| Request rate / 5xx rate | `django_http_requests_total_by_method_total`, `django_http_responses_total_by_status_total` |
| p95 latency | `django_http_requests_latency_seconds_by_view_method_bucket` |
| WebSocket handshakes | `django_channels_websocket_handshake_requests_total` |
| RabbitMQ queue depth | `rabbitmq_queue_messages` |
| Redis memory / hit rate | `redis_memory_used_bytes`, `redis_keyspace_hits_total` |
| Postgres connections | `pg_stat_activity_count` |
| Celery task rate | `celery_task_succeeded_total` |

A separate **Ranking** dashboard shows feature drift (PSI), fallbacks and scoring latency, with alert rules in
`monitoring/prometheus/rules/`. `/metrics` is only reachable inside the Docker network.

---

## Project structure

```
andromeda-web/
├── server/                    Django backend
│   ├── andromeda/             settings, URLs, ASGI, Celery app
│   ├── core/                  permissions, visibility, upload validation, throttles,
│   │                          WebSocket tickets, global search, seed command, security tests
│   ├── users/                 auth, sessions, profiles, privacy, friends, blocking, graph sync
│   ├── posts/                 posts, reactions, comments, hashtags, mentions, link previews
│   ├── chats/                 rooms, messages, attachments, WebSocket consumer, ticket auth
│   ├── notifications/         model, Celery tasks, WebSocket consumer
│   ├── groups/  pages/        groups, roles and join requests; pages, admins and follows
│   ├── marketplace/           listings, images, categories, reviews
│   ├── watch/                 videos, HLS, captions, chapters, views, likes, comments
│   ├── moderation/            reports, cases, actions, appeals
│   ├── retrieval/             embeddings, hybrid search, Ask, retrieval evals
│   ├── ranking/               impressions, features, LightGBM training and serving, A/B, drift
│   └── assistant/             agent runs, tools, proposals, audit, MCP endpoint
├── client/src/app/            Angular frontend
│   ├── core/                  auth (in-memory session), API, WebSocket, guards, interceptor
│   ├── features/              lazy routes: feed, chat, profile, groups, search, settings, …
│   ├── shared/                navbar, post card, composer, image cropper
│   └── models/                TypeScript interfaces
├── ai/                        AI service: gateway, features, guardrails, evals, distillation, fine-tuning
├── monitoring/                Prometheus config, Grafana provisioning and dashboards
├── docker-compose.yml         full stack
└── dev.sh / dev.ps1           hybrid local dev launcher
```

---

## Contributing

1. Branch from `main` and use Conventional Commits (`feat:`, `fix:`,
   `chore:`, `docs:`).
2. Every new endpoint needs an authorization test showing that a stranger,
   a blocked user and a non-member can't read or change data they shouldn't.
   Add it to `core/test_security.py` or next to the feature.
3. Run `pytest`, `ruff check .` and `npm run test:ci` before opening a PR.

## License

[MIT](LICENSE)
