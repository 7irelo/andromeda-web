#!/usr/bin/env bash
# Nightly encrypted backups of Postgres and Neo4j to an S3 bucket (MinIO or any S3).
#
# Run on the Docker host from the repository checkout, e.g. from cron:
#   15 2 * * *  cd /srv/andromeda && ./scripts/backup.sh >> /var/log/andromeda-backup.log 2>&1
#
# Environment (keep it in a root-only file, e.g. /etc/andromeda/backup.env):
#   BACKUP_AGE_RECIPIENT   age public key (age1...). Only the public key lives on the server;
#                          the private key needed to restore is kept offline.
#   BACKUP_S3_URL          e.g. https://s3.eu-west-1.amazonaws.com, or http://minio:9000 (same host,
#                          not off-site: prefer a different provider/region)
#   BACKUP_S3_ACCESS_KEY / BACKUP_S3_SECRET_KEY
#                          credentials allowed to write (and list/delete for retention) the bucket only
#   BACKUP_BUCKET          default andromeda-backups
#   BACKUP_PREFIX          default the host name
#   BACKUP_RETENTION_DAYS  default 14
#   COMPOSE_FILES          default "docker-compose.yml docker-compose.prod.yml"
#
# Dumps are streamed: pg_dump | age | mc pipe. Nothing unencrypted touches disk.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${BACKUP_AGE_RECIPIENT:?Set BACKUP_AGE_RECIPIENT (age public key)}"
: "${BACKUP_S3_URL:?Set BACKUP_S3_URL}"
: "${BACKUP_S3_ACCESS_KEY:?Set BACKUP_S3_ACCESS_KEY}"
: "${BACKUP_S3_SECRET_KEY:?Set BACKUP_S3_SECRET_KEY}"
BUCKET="${BACKUP_BUCKET:-andromeda-backups}"
PREFIX="${BACKUP_PREFIX:-$(hostname -s)}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

compose_args=()
for f in ${COMPOSE_FILES:-docker-compose.yml docker-compose.prod.yml}; do compose_args+=(-f "$f"); done
compose() { docker compose "${compose_args[@]}" "$@"; }

# mc reads the alias from MC_HOST_backup; passing it with -e NAME keeps the secret out of argv.
scheme="${BACKUP_S3_URL%%://*}"
export MC_HOST_backup="${scheme}://${BACKUP_S3_ACCESS_KEY}:${BACKUP_S3_SECRET_KEY}@${BACKUP_S3_URL#*://}"
export BACKUP_AGE_RECIPIENT
tools() { compose --profile tools run --rm -T -e MC_HOST_backup -e BACKUP_AGE_RECIPIENT backup-tools "$@"; }
upload() { tools sh -c 'age -r "$BACKUP_AGE_RECIPIENT" | mc pipe --quiet "$1"' sh "$1"; }

log() { echo "$(date -u +%FT%TZ) backup: $*"; }

log "postgres -> $PREFIX/postgres/$STAMP.dump.age"
compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' \
  | upload "backup/$BUCKET/$PREFIX/postgres/$STAMP.dump.age"

# Neo4j Community can only dump a stopped database. The graph is a read model
# (the app degrades to relational fallbacks and the outbox queues writes), so a
# short stop is safe; reconciliation can also rebuild it from Postgres.
log "neo4j -> $PREFIX/neo4j/$STAMP.dump.age (graph stopped meanwhile)"
compose stop neo4j
trap 'compose start neo4j >/dev/null' EXIT
compose run --rm -T --no-deps --entrypoint neo4j-admin neo4j database dump neo4j --to-stdout \
  | upload "backup/$BUCKET/$PREFIX/neo4j/$STAMP.dump.age"
compose start neo4j
trap - EXIT

log "retention: removing backups older than ${RETENTION_DAYS} days"
tools mc rm --recursive --force --older-than "${RETENTION_DAYS}d" "backup/$BUCKET/$PREFIX/" || true
tools mc ls --recursive "backup/$BUCKET/$PREFIX/" | tail -n 4
log "done"
