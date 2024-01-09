# Andromeda

> A Facebook-like full-stack social media platform.

[![CI](https://github.com/your-org/andromeda-web/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/andromeda-web/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2-green.svg)](https://djangoproject.com/)
[![Angular](https://img.shields.io/badge/angular-17-red.svg)](https://angular.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development](#local-development)
- [Testing](#testing)
- [Monitoring](#monitoring)
- [CI/CD](#cicd)
- [Contributing](#contributing)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Angular 17 (standalone components) + Angular Material |
| Backend | Django 4.2 + Django REST Framework + Django Channels |
| Graph DB | Neo4j 5 — social graph, friend recommendations |
| Relational DB | PostgreSQL 15 |
| Cache / Channels | Redis 7 |
| Message Queue | RabbitMQ 3 + Celery 5 |
| WebSockets | Django Channels — real-time chat & notifications |
| Monitoring | Prometheus + Grafana |
| Reverse Proxy | Nginx |
| Containers | Docker + Docker Compose |

---

## Features

| Feature | Details |
|---|---|
| Authentication | JWT register / login / logout with silent token refresh |
| News Feed | Posts from followed users with infinite scroll |
| Post Reactions | Like, Love, Haha, Wow, Sad, Angry |
| Comments | Threaded comments with replies |
| Real-time Chat | WebSocket DMs and group chats, typing indicators, read receipts |
| Notifications | Real-time WebSocket push delivered via RabbitMQ + Celery |
| Friend Requests | Send, accept, decline |
| Follow System | Directed follow relationships |
| Social Graph | Neo4j powers friends-of-friends recommendations |
| Groups | Public / Private / Secret groups |
| Marketplace | Buy & sell listings with image galleries |
| Watch | Video feed with likes and comments |
| Pages | Business / community pages |
| Monitoring | Prometheus metrics with a pre-provisioned Grafana dashboard |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (Angular 17)                                        │
│    HTTP/REST ──► Nginx ──► Django (DRF + ASGI/uvicorn)      │
│    WebSocket ───────────► Django Channels ──► Redis          │
└─────────────────────────────────────────────────────────────┘
                               │
              ┌────────────────┼──────────────────┐
              ▼                ▼                  ▼
         PostgreSQL          Neo4j           RabbitMQ
         (relational)     (social graph)    (task broker)
                                                  │
                                             Celery Workers
                                     (notifications · emails · messages)

Prometheus scrapes: Django /metrics · Redis exporter · Postgres exporter · RabbitMQ
Grafana visualises all of the above on the Andromeda Overview dashboard.
```

---

## Project Structure

```
andromeda-web/
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI pipeline
├── docker-compose.yml
├── .env.example
├── server/                      # Django backend
│   ├── andromeda/               # Project settings, urls, asgi, celery
│   ├── users/                   # Auth, friend requests, follows, Neo4j sync
│   ├── posts/                   # Posts, reactions, comments
│   ├── chats/                   # Rooms, messages, WebSocket consumers
│   ├── notifications/           # Notification model, Celery tasks, WS consumer
│   ├── groups/                  # Group membership
│   ├── marketplace/             # Listings, reviews
│   ├── watch/                   # Videos
│   └── pages/                   # Business / community pages
├── client/                      # Angular 17 frontend
│   └── src/app/
│       ├── core/                # Auth service, interceptors, guards
│       ├── features/            # Lazy-loaded pages (feed, chat, profile …)
│       ├── shared/              # Reusable components (post-card, navbar …)
│       └── models/              # TypeScript interfaces
└── monitoring/
    ├── prometheus/prometheus.yml
    └── grafana/
        ├── provisioning/        # Auto-provisioned datasource & dashboard
        └── dashboards/          # Andromeda Overview JSON
```

---

## Quick Start (Docker)

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) ≥ 24

### 1. Configure environment

```bash
cp .env.example .env
# Open .env and change the secret values before running in production
```

### 2. Start everything

```bash
docker compose up --build
```

All services start automatically. Django runs migrations on first boot.

### 3. Open the app

| Service | URL | Default credentials |
|---|---|---|
| **App** (Angular) | http://localhost | — |
| **API** | http://localhost:8000/api/ | — |
| **Django Admin** | http://localhost:8000/admin/ | create with step 4 |
| **Grafana** | http://localhost:3000 | admin / admin\_secret |
| **Prometheus** | http://localhost:9090 | — |
| **RabbitMQ** | http://localhost:15672 | andromeda / andromeda\_secret |
| **Celery Flower** | http://localhost:5555 | — |
| **Neo4j Browser** | http://localhost:7474 | neo4j / andromeda\_secret |

### 4. Create a superuser

```bash
docker compose exec django python manage.py createsuperuser
```

### 5. Stop

```bash
docker compose down          # keep volumes
docker compose down -v       # also wipe all data
```

---

## Local Development

### Backend

```bash
cd server
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start supporting services (Postgres, Redis, RabbitMQ) via Docker
docker compose up postgres redis rabbitmq neo4j -d

export DJANGO_SETTINGS_MODULE=andromeda.settings
export POSTGRES_HOST=localhost
export REDIS_URL=redis://:redis_secret@localhost:6379/0
export RABBITMQ_URL=amqp://andromeda:andromeda_secret@localhost:5672/andromeda
export NEO4J_BOLT_URL=bolt://neo4j:andromeda_secret@localhost:7687

python manage.py migrate
python manage.py runserver

# Celery worker (separate terminal, same env vars)
celery -A andromeda worker --loglevel=info
```

### Frontend

```bash
cd client
npm install
npm start          # http://localhost:4200, proxies /api → :8000, /ws → :8000
```

---

## Testing

### Backend (Django + pytest)

Tests use an in-memory SQLite database and stub out Neo4j / Redis / RabbitMQ so
no external services are needed.

```bash
cd server
pip install -r requirements.txt
pytest --ds=andromeda.settings_test -v
```

To also measure coverage:

```bash
pytest --ds=andromeda.settings_test --cov=. --cov-report=term-missing
```

### Frontend (Angular + Karma)

```bash
cd client
npm install
npm test                            # watch mode
npm run test:ci                     # single-run, headless Chrome (used in CI)
```

### Full stack (Docker)

```bash
# Backend
docker compose run --rm django pytest --ds=andromeda.settings_test -v

# Frontend
docker compose run --rm client npm run test:ci
```

---

## Monitoring

Grafana is pre-provisioned at **http://localhost:3000** (admin / admin\_secret).

The **Andromeda Overview** dashboard displays:

| Panel | Metric source |
|---|---|
| HTTP request rate | `django_http_requests_total_by_method_total` |
| HTTP error rate (5xx) | `django_http_responses_total_by_status_total` |
| Response time p95 | `django_http_requests_latency_seconds_by_view_method_bucket` |
| Active WebSocket connections | `django_channels_websocket_handshake_requests_total` |
| RabbitMQ queue depth | `rabbitmq_queue_messages` |
| Redis memory / hit rate | `redis_memory_used_bytes`, `redis_keyspace_hits_total` |
| PostgreSQL connections | `pg_stat_activity_count` |
| Celery task rate | `flower_tasks_total` |

---

## CI/CD

The GitHub Actions pipeline (`.github/workflows/ci.yml`) runs on every push and
pull-request to `main`:

| Job | What it does |
|---|---|
| `backend-test` | Installs deps, runs `pytest` against PostgreSQL service container |
| `frontend-test` | `npm ci`, headless Karma tests, production `ng build` |
| `docker-build` | `docker compose build` — validates both Dockerfiles |

All three jobs must pass before a PR can be merged.

---

## Contributing

1. Fork the repository and create a feature branch from `main`.
2. Write tests for any new behaviour.
3. Make sure `pytest` (backend) and `npm run test:ci` (frontend) both pass locally.
4. Open a pull request — the CI pipeline runs automatically.

### Commit style

```
feat: add video reactions
fix: correct unread notification count on WS reconnect
chore: bump django to 4.2.11
```

---

## License

[MIT](LICENSE)
