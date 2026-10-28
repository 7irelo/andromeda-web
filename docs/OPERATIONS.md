# Operations

How Andromeda runs in production: deploying, releasing, backups and restores,
observability and alerts, and the background machinery (outbox, feed cache,
video pipeline) that needs an operator now and then.

## Production stack

`docker-compose.prod.yml` is an overlay on `docker-compose.yml`:

```
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

- **Caddy** terminates TLS for `DOMAIN` (automatic certificates, HTTP to HTTPS
  redirect, HSTS for a year) and proxies to the client nginx. It is the only
  service with published ports (80, 443 and 443/udp for HTTP/3). CI fails if
  any other service publishes a port in the overlay.
- Everything else is internal to the `andromeda_network` bridge: Postgres,
  Neo4j, Redis, RabbitMQ, MinIO, the exporters, Prometheus, Grafana and
  Alertmanager.
- Application containers (Django, Celery, Flower, AI, client) run from GHCR
  images, as non-root (except nginx's master), with read-only root
  filesystems, `cap_drop: ALL`, `no-new-privileges`, CPU/memory limits,
  `restart: always` and rotated JSON logs. The video worker gets a scratch
  volume for ffmpeg instead of tmpfs.
- `DEBUG=False`, `SECURE_SSL_REDIRECT=True` and HSTS are set by the overlay;
  `/metrics` and `/api/health/` are exempt from the redirect for internal
  plain-HTTP callers (Prometheus, health checks).

### Server `.env`

Start from `.env.example`. In production set at least:

| Variable | Notes |
|---|---|
| `DOMAIN`, `ACME_EMAIL` | public host name and certificate contact (Caddy) |
| `SECRET_KEY` | 50+ random characters |
| `ALLOWED_HOSTS` | `<DOMAIN>,localhost,django` (`localhost` for the health check, `django` for Prometheus) |
| `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_URL` | `https://<DOMAIN>` |
| `MINIO_EXTERNAL_URL` | `https://<DOMAIN>/media` |
| `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, `REDIS_PASSWORD`, `RABBITMQ_PASSWORD`, `MINIO_ROOT_PASSWORD`, `GRAFANA_PASSWORD`, `FLOWER_PASSWORD`, `AI_SERVICE_SECRET` | all different, all random |
| `IMAGE_REGISTRY`, `IMAGE_TAG` | default `ghcr.io/7irelo` and `latest`; the deploy job sets `IMAGE_TAG` |
| `SENTRY_DSN`, `SENTRY_FRONTEND_DSN` | optional, see [Errors](#errors-sentry) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | optional, see [Tracing](#tracing) |
| `ALERTMANAGER_WEBHOOK_URL` (and `ALERTMANAGER_SMTP_PASSWORD`) | see [Alerts](#alerts) |

The overlay refuses to start (`${VAR:?}`) when the passwords it needs are missing.

### Reaching the internal dashboards

Nothing but Caddy listens on the host, so use an SSH tunnel to the container's
address on the Docker bridge:

```
ssh -L 3000:$(ssh prod "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' andromeda_grafana"):3000 prod
# then open http://localhost:3000 (Prometheus :9090, Alertmanager :9093, Flower :5555 the same way)
```

## Releasing and deploying

1. Tag a release: `git tag v1.4.0 && git push origin v1.4.0`.
2. `.github/workflows/release.yml` builds the server, AI and client images and
   pushes them to GHCR as `ghcr.io/<owner>/andromeda-{server,ai,client}:1.4.0`
   (and `1.4`), with max-mode build provenance, an SBOM and a signed
   provenance attestation.
3. Deploy by running the **Release** workflow by hand with `tag: v1.4.0`. The
   `deploy` job uses the `production` environment (add required reviewers in
   the repository settings) and, over SSH with a pinned host key:
   - checks out the tag on the server,
   - runs `scripts/release.sh`: pulls the images, makes sure the data services
     are up, and runs the one-shot `migrate` service (profile `release`:
     `migrate`, `collectstatic`, `check --deploy`),
   - then `docker compose ... up -d --remove-orphans --wait`.

Secrets the deploy job expects (documented, not created): `DEPLOY_HOST`,
`DEPLOY_USER` (in the docker group), `DEPLOY_SSH_KEY` (a deploy-only ed25519
key), `DEPLOY_KNOWN_HOSTS` (`ssh-keyscan -t ed25519 <host>`), `DEPLOY_PATH`.
The server logs in to GHCR once with a read-only token:
`echo "$TOKEN" | docker login ghcr.io -u <user> --password-stdin`.

Migrations run before the new containers start while the old ones still
serve, so they must be backwards compatible (expand, then contract a release later).

## Backups

`scripts/backup.sh` (run by cron or a systemd timer on the host) writes:

- **Postgres:** `pg_dump -Fc` (custom format),
- **Neo4j:** `neo4j-admin database dump` (Community can only dump a stopped
  database, so the graph is stopped for the dump; the app degrades to its
  relational fallbacks and the outbox holds graph writes until it's back),

each streamed through `age` (encrypted to `BACKUP_AGE_RECIPIENT`, a public
key) straight into `s3://$BACKUP_BUCKET/$BACKUP_PREFIX/{postgres,neo4j}/<UTC timestamp>.dump.age`.
Nothing unencrypted is written to disk. Backups older than
`BACKUP_RETENTION_DAYS` (default 14) are deleted.

```
# /etc/andromeda/backup.env  (root:root 0600)
BACKUP_AGE_RECIPIENT=age1...
BACKUP_S3_URL=https://s3.eu-west-1.amazonaws.com
BACKUP_S3_ACCESS_KEY=...
BACKUP_S3_SECRET_KEY=...
BACKUP_BUCKET=andromeda-backups

# crontab -e (root)
15 2 * * *  set -a; . /etc/andromeda/backup.env; set +a; cd /srv/andromeda && ./scripts/backup.sh >> /var/log/andromeda-backup.log 2>&1
```

- Generate the key pair **offline**: `age-keygen -o andromeda-backup.key`.
  Put only the `age1...` public key on the server; keep the private key in a
  password manager or hardware-backed vault. A stolen server can't read old backups.
- Use a bucket in another account/region (the local `andromeda-backups`
  MinIO bucket exists for drills, but it's on the same disk), with
  credentials that can only write to it, and versioning/object lock if the
  provider has it.

## Restoring

`scripts/restore.sh` reverses the pipeline (`mc cat | age -d | pg_restore` /
`neo4j-admin database load`). Bring the private key only for the restore and
delete it afterwards.

```
export AGE_IDENTITY_FILE=~/andromeda-backup.key       # chmod 600
set -a; . /etc/andromeda/backup.env; set +a
files="-f docker-compose.yml -f docker-compose.prod.yml"

docker compose $files stop django celery_worker celery_video celery_beat flower
scripts/restore.sh postgres latest            # or postgres/20261028T021500Z.dump.age
scripts/restore.sh neo4j latest               # optional: the graph can be rebuilt instead
IMAGE_TAG=<running version> scripts/release.sh
docker compose $files up -d
docker compose $files exec django python manage.py reconcile_graph   # bring Neo4j in line with Postgres
```

To check a backup without touching production, restore into another
database: `scripts/restore.sh postgres latest andromeda_check` (create it
first with `createdb`).

### Restore drill

`scripts/restore-drill.sh` runs the whole cycle against throwaway containers
(scratch Postgres, Neo4j and MinIO on their own network, a throwaway age key):
seed data, back up exactly like `backup.sh`, restore into empty containers
exactly like `restore.sh`, and compare row/node counts and a content
checksum. Run it after changing anything in the backup path, and quarterly.
`DRILL_NEO4J=0` skips the graph.

| Date | Who / where | Postgres | Neo4j | Result |
|---|---|---|---|---|
| 2026-10-28 | local, Docker Desktop 29.5 (Windows), `scripts/restore-drill.sh` | 2000 users / 10000 posts / 8000 likes; content checksum `b940919668575dc5796c803593d977f3` identical after restore; 287 KiB encrypted dump (`age-encryption.org/v1` header checked); restored in 12 s | 800 nodes / 499 relationships identical after restore; 43 KiB encrypted dump; load + start-up 102 s | **Passed** |

Lesson from the first drill run: `neo4j-admin database dump` refuses a
database that wasn't shut down cleanly ("Active logical log detected"), and
Docker's default 10 s stop timeout can kill Neo4j before it checkpoints. The
scripts now stop it with `-t 120` and the overlay sets `stop_grace_period: 2m`.

## Observability

### Request ids and logs

nginx gives every request an id (`$request_id`), logs it, and passes it to
Django as `X-Request-ID`. Django keeps a sane inbound id (8-128 of
`[A-Za-z0-9._:-]`, anything else is replaced), returns it in the
`X-Request-ID` response header, stamps it on every log line, copies it into
the headers of Celery tasks queued during the request (workers log it too)
and sends it to the AI service, which logs it and echoes it back. Logs are one
JSON object per line (`LOG_FORMAT=text` for a readable console in development),
with `trace_id`/`span_id` when tracing is on. To follow one request:

```
docker compose logs django celery_worker ai | grep 4f3c2b1a0e9d8c7b6a5f4e3d2c1b0a99
```

### Tracing

Off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Locally:

```
docker compose --profile observability up -d otel-collector jaeger
# .env: OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318, then recreate django/celery/ai
open http://127.0.0.1:16686
```

Spans cover Django requests, Celery tasks, WebSocket connections (Channels),
outbound calls to the AI service, and each model call in the AI gateway with
the OpenTelemetry GenAI conventions (`gen_ai.system`, `gen_ai.request.model`,
`gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`) plus `ai.job`,
`ai.cost_usd` and `ai.prompt_hash`. Prompts and responses are never recorded:
the prompt hash is an HMAC keyed with the service secret, exception messages
(which can echo provider input) are not attached, and URLs lose their query
strings (search terms, WebSocket tickets). The collector deletes auth headers,
cookies, query strings, SQL statements and GenAI message attributes as a
second line of defence. Sampling follows the standard `OTEL_TRACES_SAMPLER` variables.

### Errors (Sentry)

- Backend (Django, Celery, AI service): set `SENTRY_DSN`. Automatic data
  collection is off (sentry-sdk's `data_collection`, which supersedes the
  deprecated `send_default_pii=False`: no user info, cookies, headers, bodies,
  query params, SQL parameters, task arguments or local variables) and
  `before_send` strips auth headers, cookies, bodies and query strings again.
- Frontend: build the client image with `SENTRY_FRONTEND_DSN` (a build arg;
  DSNs are public by design) and set the same value in the server `.env`.
  The SDK is lazy-loaded only when a DSN is present, sends through the
  same-origin relay `POST /api/errors/` (the CSP allows `connect-src 'self'`
  only), and the relay forwards only envelopes for that DSN to that DSN's host.

### Alerts

Rules live in `monitoring/prometheus/rules/andromeda.yml` and route through
Alertmanager (`monitoring/alertmanager/alertmanager.yml`):

| Alert | Fires when |
|---|---|
| `ApiLatencyP95High` / `Critical` | API p95 > 500 ms for 10 min / > 1.5 s for 5 min |
| `Api5xxRateHigh` / `Critical` | 5xx share > 1% / > 5% for 5 min |
| `CeleryQueueBacklog`, `VideoQueueBacklog`, `CeleryWorkersDown` | queue depth > 200 (video > 20) / no workers reporting |
| `WebSocketDisconnectRateHigh` | > 25% of WebSocket disconnects are abnormal (1006) or errors |
| `AiSpendSpike`, `AiDailySpendHigh` | last hour > 3x the weekly hourly average (and > $1) / > $50 in 24 h |
| `OutboxLagging`, `OutboxStalled`, `OutboxDeadLetters` | oldest pending graph event > 5 min / > 30 min / any dead letter |
| `GraphDriftDetected`, `GraphReconcileStale` | nightly reconciliation repaired > 50 items / hasn't run in 2 days |
| `ScrapeTargetDown` | an exporter or service isn't scraped for 5 min |

Receivers: set `ALERTMANAGER_WEBHOOK_URL` to any endpoint that accepts the
Alertmanager webhook JSON (a Slack/Teams/Discord bridge, PagerDuty Events
via its webhook integration, or your own). For email, fill in the commented
`email_configs` block and set `ALERTMANAGER_SMTP_PASSWORD`. Secrets are written
to files inside the container at start-up, never into the config. Without a
receiver, alerts still show in Alertmanager and on the **Andromeda – SLOs &
Alerts** Grafana dashboard, which has a panel for each.

Note: Django runs several uvicorn workers and each scrape reaches one of
them, so its counters are sampled. Ratios and quantiles (what the alerts use)
are stable; absolute request rates are indicative.

## Background machinery

### Neo4j projection (transactional outbox)

Graph changes are recorded as `OutboxEvent` rows in the same transaction as
the change and drained every 5 s by `outbox.tasks.drain_outbox` (beat), in id
order, with `SELECT ... FOR UPDATE SKIP LOCKED`. Failures back off
exponentially with jitter (5 s doubling to an hour) and dead-letter after
`OUTBOX_MAX_ATTEMPTS` (12).

- Dead letters: fix the cause, then **Admin > Outbox events > Retry selected**
  (or `drain.requeue_dead()` from a shell).
- `manage.py reconcile_graph [--dry-run]` compares users, accepted
  friendships, posts and likes with the graph in id ranges and repairs drift;
  it also runs nightly (03:40 UTC). Use it after restoring Postgres or
  rebuilding Neo4j from scratch.
- Processed events are purged after 7 days. With `NEO4J_ENABLED=False` events
  are still written and immediately marked processed.

### Feed cache

Redis inboxes of candidate post ids (`server/feedcache/`). Tunables:
`FEEDCACHE_ENABLED`, `FEEDCACHE_FANOUT_THRESHOLD` (default 1000: larger
audiences are merged at read time), `FEEDCACHE_MAX_ITEMS` (500),
`FEEDCACHE_TTL_SECONDS` (3 days). Flushing Redis is always safe: inboxes
rebuild from Postgres on the next read, and candidates are filtered through
`core.visibility` regardless.

### Video uploads and legacy videos

- Large uploads: the client asks `POST /api/watch/uploads/` for a presigned
  POST policy (random key under `private/uploads/`, pinned type and size),
  uploads to `/media-upload/` (nginx, POST only, to MinIO), then calls
  `POST /api/watch/uploads/complete/`, which checks size, type and magic bytes
  before processing. Abandoned uploads expire after a day (bucket lifecycle rule).
- `manage.py reprocess_videos [--dry-run] [--limit N]` queues videos uploaded
  before the HLS pipeline and moves non-public originals out of `public/`.
  Run it again with `--move-public` once they're processed to take public
  originals private too.
- RabbitMQ's consumer timeout is 3 h (`deploy/rabbitmq/20-andromeda.conf`) so
  the single-slot video worker's prefetched message isn't reclaimed during a
  long transcode.
- Image variants (thumb/medium WebP) are generated on upload;
  `manage.py generate_image_variants` backfills older avatars and post images.
