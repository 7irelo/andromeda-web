# Andromeda

> A full-stack social platform: feed, real-time chat, groups, marketplace,
> video and pages. It is built on Django, Angular, Postgres, a Neo4j social
> graph and an event-driven Celery backbone. It is also being built into an
> **AI-native** platform, with semantic search, safety, summarisation, an
> agentic assistant and voice.

[![CI](https://github.com/7irelo/andromeda-web/actions/workflows/ci.yml/badge.svg)](https://github.com/7irelo/andromeda-web/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2-green.svg)](https://djangoproject.com/)
[![Angular](https://img.shields.io/badge/angular-17-red.svg)](https://angular.dev/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

![Andromeda: feed, chat, marketplace, profile, API, monitoring](docs/screenshots/andromeda-ui.png)

---

## Project status

**Active development. Not production-ready.**

Andromeda has a broad feature surface and solid infrastructure, but several
features are only partly built, and authorization is incomplete (see the
[audit in the roadmap](docs/ROADMAP.md#audit-findings)). **Don't deploy it
with real user data yet.**

| Plan | What it covers |
|---|---|
| 📋 [**Completion roadmap**](docs/ROADMAP.md) | Security fixes, finishing every feature, polish, trust & safety, scale |
| 🤖 [**AI integration plan**](docs/AI_PLAN.md) | AI architecture, per-job model selection (Anthropic + OpenAI), evals, LLMOps, safety, voice |

---

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Quick start (Docker)](#quick-start-docker)
- [Local development](#local-development)
- [Testing](#testing)
- [Monitoring](#monitoring)
- [Project structure](#project-structure)
- [Contributing](#contributing)

---

## Features

✅ working · 🟡 partial · 🔜 planned

| Area | Status | Today | Next ([roadmap](docs/ROADMAP.md)) |
|---|---|---|---|
| **Auth** | 🟡 | JWT register/login/logout, silent refresh, account deletion | Password change and reset, email verification, sessions, 2FA |
| **Feed & posts** | 🟡 | Text/image/video posts, 6 reactions, comments with replies, sharing, infinite scroll, search | Visibility enforcement, multi-image, link previews, mentions/hashtags, editing UI |
| **Friends** | 🟡 | Requests (send/accept/decline/cancel), suggestions from the Neo4j graph | Unfriend, friends lists, blocking, explained suggestions |
| **Chat** | 🟡 | WebSocket DMs and group rooms, typing indicators, read receipts, presence | Room-scoped permissions, attachments, edit/delete, reactions, reconnect sync |
| **Notifications** | ✅ | Real-time push via Celery + RabbitMQ → Channels, unread counts | Preferences, digests, Web Push, grouping |
| **Groups** | 🟡 | Create, join/leave public groups, members list | Join requests, roles, group feed, private/secret enforcement |
| **Marketplace** | 🟡 | Listings with image galleries, categories, price filters, likes | Edit/sold flow, message seller, saved listings, reviews UI |
| **Watch** | 🟡 | Video upload, playback, likes, comments | Transcoding to HLS, thumbnails, captions, watch history |
| **Pages** | 🟡 | Create, list, follow/unfollow | Page detail, admins, posting as a page |
| **Settings** | 🟡 | Profile editing, privacy preferences, dark mode | Server-side enforcement of privacy settings |
| **Monitoring** | ✅ | Prometheus metrics + pre-provisioned Grafana dashboard | Tracing, SLO alerts, error tracking |
| **AI** | 🔜 | — | Semantic search, moderation, Catch Me Up, assistant, voice ([plan](docs/AI_PLAN.md)) |

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Angular 17 (standalone components), Angular Material, RxJS |
| API | Django 4.2, Django REST Framework, SimpleJWT |
| Real-time | Django Channels over Redis (chat, notifications, presence) |
| Relational DB | PostgreSQL 15 |
| Social graph | Neo4j 5 (friend-of-friend suggestions, mutual friends) |
| Async work | Celery 5 + RabbitMQ 3 (queues: `notifications`, `messages`, `emails`, `default`), Celery Beat, Flower |
| Cache | Redis 7 |
| Media | MinIO (S3-compatible), with local storage as the fallback |
| Observability | Prometheus, Grafana, Redis and Postgres exporters |
| Delivery | Docker Compose, Nginx (serves the Angular build), GitHub Actions |
| *Planned AI* | FastAPI service, pgvector, Temporal, Langfuse, Anthropic + OpenAI behind a provider gateway |

> Django 4.2 and Angular 17 are past end of support. Upgrading them is part of
> [Phase 0](docs/ROADMAP.md#phase-0--foundations--security--3-weeks-).

---

## Architecture

```
                     ┌───────────────────────────────┐
  Browser ─ HTTP ──► │ Nginx  (Angular static build) │
  (Angular)          └───────────────┬───────────────┘
     │                               │ /api
     │ WebSocket /ws                 ▼
     └──────────────────►  Django (DRF + Channels, ASGI/uvicorn)
                              │        │          │
                              ▼        ▼          ▼
                         PostgreSQL  Neo4j     Redis ◄── channel layer
                                                 ▲
                              RabbitMQ ──► Celery workers ┘
                              (notifications · messages · emails)

  MinIO: media      Prometheus ◄── /metrics, exporters ──► Grafana
```

- **Writes** go to Postgres. Signals mirror users, friendships and posts into
  Neo4j for graph queries.
- **Side effects** (notifications, offline message alerts, emails) go to
  Celery through RabbitMQ. Workers push to users through the Channels layer.
- **Chat** is a Channels consumer per room. Messages are persisted, then
  broadcast to the room group.

The planned AI architecture is in [AI_PLAN §1](docs/AI_PLAN.md#1-architecture).

---

## Quick start (Docker)

**Requirements:** Docker Desktop ≥ 24.

```bash
cp .env.example .env          # change the secrets before any real deployment
docker compose up --build
```

Migrations run automatically on first boot. Then:

```bash
docker compose exec django python manage.py createsuperuser
```

| Service | URL | Default credentials (from `.env.example`) |
|---|---|---|
| App | http://localhost | register an account |
| API | http://localhost:8000/api/ | JWT |
| Django admin | http://localhost:8000/admin/ | your superuser |
| Grafana | http://localhost:3000 | `admin` / `admin_secret` |
| Prometheus | http://localhost:9090 | — |
| RabbitMQ | http://localhost:15672 | `andromeda` / `andromeda_secret` |
| Flower | http://localhost:5555 | — |
| Neo4j Browser | http://localhost:7474 | `neo4j` / `andromeda_secret` |

```bash
docker compose down        # stop, keep data
docker compose down -v     # stop and wipe all volumes
```

---

## Local development

Run the infrastructure in Docker and the app processes natively, with hot
reload:

```bash
bash dev.sh                # macOS / Linux / Git Bash   flags: --no-client --no-celery --reset-db
.\dev.ps1                  # Windows PowerShell         flags: -NoClient -NoCelery -ResetDb
```

<details>
<summary>Manual setup</summary>

**Backend**

```bash
docker compose up -d postgres redis rabbitmq neo4j minio

cd server
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export POSTGRES_HOST=localhost
export REDIS_URL=redis://:redis_secret@localhost:6379/0
export RABBITMQ_URL=amqp://andromeda:andromeda_secret@localhost:5672/andromeda
export NEO4J_BOLT_URL=bolt://neo4j:andromeda_secret@localhost:7687

python manage.py migrate
python manage.py runserver
celery -A andromeda worker -l info      # separate terminal, same env
celery -A andromeda beat -l info        # optional: periodic tasks
```

**Frontend**

```bash
cd client
npm install
npm start      # http://localhost:4200, proxies /api and /ws to :8000
```

</details>

---

## Testing

**Backend** uses pytest-django. The test settings use in-memory SQLite and
stub out Neo4j, Redis and RabbitMQ, so no services are needed.

```bash
cd server
pip install -r requirements.txt
pytest                                   # settings come from pytest.ini
pip install pytest-cov && pytest --cov=. --cov-report=term-missing
```

**Frontend** uses Karma and Jasmine:

```bash
cd client
npm test           # watch mode
npm run test:ci    # single run, headless Chrome
```

**CI** (`.github/workflows/ci.yml`) currently runs `manage.py check`, a Python
compile check, the Angular production build and a Docker Compose build. It
**doesn't run the test suites yet**. Adding lint, type checks, tests with a
coverage gate, E2E and security scans is
[roadmap item 0.6](docs/ROADMAP.md#06-real-ci--m).

---

## Monitoring

Grafana (http://localhost:3000) ships with the **Andromeda Overview**
dashboard:

| Panel | Metric |
|---|---|
| Request rate / 5xx rate | `django_http_requests_total_by_method_total`, `django_http_responses_total_by_status_total` |
| p95 latency | `django_http_requests_latency_seconds_by_view_method_bucket` |
| WebSocket handshakes | `django_channels_websocket_handshake_requests_total` |
| RabbitMQ queue depth | `rabbitmq_queue_messages` |
| Redis memory / hit rate | `redis_memory_used_bytes`, `redis_keyspace_hits_total` |
| Postgres connections | `pg_stat_activity_count` |
| Celery task rate | `flower_tasks_total` |

AI-specific panels (tokens, cost, latency and fallback rate per feature) are
planned in [AI_PLAN §3.2](docs/AI_PLAN.md#32-observability).

---

## Project structure

```
andromeda-web/
├── server/                    Django backend
│   ├── andromeda/             settings, URLs, ASGI, Celery app
│   ├── users/                 auth, profiles, privacy, friend requests, Neo4j models + sync
│   ├── posts/                 posts, reactions, comments, tags
│   ├── chats/                 rooms, messages, WebSocket consumer, JWT WS middleware
│   ├── notifications/         model, Celery tasks, WebSocket consumer
│   ├── groups/  pages/        groups and memberships, pages and follows
│   ├── marketplace/           listings, images, categories, reviews
│   └── watch/                 videos, views, likes, comments
├── client/src/app/            Angular frontend
│   ├── core/                  auth service, API service, WebSocket service, guards, interceptor
│   ├── features/              lazy-loaded routes (feed, chat, profile, groups, …)
│   ├── shared/                navbar, post card, create post, image cropper, …
│   └── models/                TypeScript interfaces
├── monitoring/                Prometheus config, Grafana provisioning and dashboards
├── docs/                      ROADMAP.md, AI_PLAN.md, screenshots
├── docker-compose.yml         full stack (15 services)
└── dev.sh / dev.ps1           hybrid local dev launcher
```

---

## Contributing

1. Branch from `main`. Use Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`).
2. Add tests for new behaviour. Every new endpoint needs a permission test
   showing that a stranger can't read or modify another user's data.
3. Run `pytest` and `npm run test:ci` locally before opening a PR.
4. Check the [roadmap](docs/ROADMAP.md) first. Phase 0 (security) items take
   priority over new features.

## License

[MIT](LICENSE)
