# Andromeda

> A full-stack social platform with a feed, real-time chat, groups, a
> marketplace, video and pages. Built on Django, Angular, PostgreSQL, a Neo4j
> social graph and an event-driven Celery backbone, with authorization and
> privacy enforced on every request, and an internal AI service for
> moderation and chat summaries.

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
| **Accounts** | Register, sign in, password change, email password reset, sign out of every device, password-confirmed account deletion |
| **Feed & posts** | Text/image/video posts, public / friends / only-me audiences, six reactions, threaded comments, sharing, #hashtags, @mentions, automatic link previews |
| **Friends** | Requests (send, accept, decline, cancel), unfriend, friends lists, blocking, suggestions from the Neo4j graph |
| **Privacy** | Per-user controls over who can see your profile, friends list and online status, who can message you or send friend requests, and whether you appear in search |
| **Chat** | Real-time DMs and group chats over WebSockets, typing indicators, read receipts, presence, private attachments, group admin tools |
| **Notifications** | Real-time push (Celery → RabbitMQ → Channels) for likes, comments, mentions and friend requests |
| **Groups** | Public, private and secret groups, a group feed, join requests with an admin approval queue, admin/moderator roles |
| **Marketplace** | Listings with image galleries, categories, price filters, saved items, reviews, Message Seller, mark sold / relist |
| **Watch** | Video upload and playback, likes, comments, one view counted per viewer |
| **Pages** | Business and community pages, follow/unfollow, posting as a page for its admins and editors |
| **Search** | One search across people, posts, groups, pages, listings and videos (Postgres full-text ranking) |
| **AI** | Automatic moderation of posts, comments and listings with a staff review queue; "Catch me up" chat summaries with verified citations |
| **Operations** | Prometheus metrics, a pre-built Grafana dashboard, OpenAPI docs, a demo-data seeder |

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
  personal data.
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
short-lived signed service tokens.

| Feature | How it works |
|---|---|
| **Moderation** | New posts, comments and listings are checked within seconds. OpenAI's free moderation endpoint runs first, then Claude Haiku 5.5 applies the community policy, and Claude Sonnet 5.5 is called only when Haiku is unsure. Clear violations are hidden (the author is notified), and borderline cases go to a staff queue at `/api/moderation/cases/` where every action is audit-logged. |
| **Catch me up** | One click in a chat summarises what you missed: topics, decisions and questions for you. Every point cites real message ids, links that weren't in the chat are removed, and blocked users' messages are never sent to the model. |
| **Assistant** | A side panel that searches, summarises and drafts for you. A Haiku router sends simple requests to fixed workflows and only open-ended ones to an agent loop (Opus plans, tools run in Django as you). Posting or sending always becomes a confirmation card you approve. Runs are durable (append-only steps on a dedicated `ai` queue), every AI-initiated write is audited, and the same tools are available to external apps over MCP with scoped personal access tokens. See [`docs/ai/adr/0001-durable-assistant-runs.md`](docs/ai/adr/0001-durable-assistant-runs.md) and [`docs/ai/mcp-security.md`](docs/ai/mcp-security.md). |

Guardrails include per-user daily token budgets, a cross-provider fallback,
circuit breakers, prompt-injection delimiting and graceful degradation when
models are unavailable. A live eval set (35 items) gates quality: the
current baseline has zero severe misses and zero false removals at
**$0.32 per 1,000 items**. See [`ai/README.md`](ai/README.md).

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Angular 22 (standalone components), Angular Material, RxJS, TypeScript 6 |
| API | Django 5.2 LTS, Django REST Framework, SimpleJWT, drf-spectacular |
| Real-time | Django Channels over Redis (chat, notifications, presence) |
| Relational DB | PostgreSQL 15 (source of truth, full-text search) |
| Social graph | Neo4j 5 (friend-of-friend suggestions, mutual friends) |
| Async work | Celery 5.5 + RabbitMQ 3 (`notifications`, `messages`, `emails`, `default` queues), Celery Beat, Flower |
| Cache | Redis 7 |
| Media | MinIO (S3-compatible), split into public and private prefixes |
| Observability | Prometheus, Grafana, Redis and Postgres exporters |
| AI | FastAPI, Pydantic, Anthropic (Claude Haiku/Sonnet 5.5) and OpenAI SDKs |
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
                (notifications · messages · emails · default)

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
# Optional: ANTHROPIC_API_KEY and OPENAI_API_KEY enable moderation and chat summaries.
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
| Celery task rate | `flower_tasks_total` |

`/metrics` is only reachable inside the Docker network.

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
│   └── watch/                 videos, views, likes, comments
├── client/src/app/            Angular frontend
│   ├── core/                  auth (in-memory session), API, WebSocket, guards, interceptor
│   ├── features/              lazy routes: feed, chat, profile, groups, search, settings, …
│   ├── shared/                navbar, post card, composer, image cropper
│   └── models/                TypeScript interfaces
├── ai/                        internal AI service: gateway, moderation, catch-up, evals
├── monitoring/                Prometheus config, Grafana provisioning and dashboards
├── docker-compose.yml         full stack (16 services)
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
