#!/usr/bin/env bash
# Restore an encrypted backup made by scripts/backup.sh.
#
#   scripts/restore.sh postgres <object|latest> [target_db]
#   scripts/restore.sh neo4j    <object|latest>
#
# <object> is the key under BACKUP_PREFIX, e.g. postgres/20261028T021500Z.dump.age.
# Needs the same BACKUP_S3_* variables as backup.sh plus
#   AGE_IDENTITY_FILE   path to the age private key (bring it from offline storage; delete after)
#
# Postgres restores into target_db (default: POSTGRES_DB) with --clean --if-exists.
# Stop the app first so nothing writes during the restore:
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml stop django celery_worker celery_video celery_beat
# then run scripts/release.sh (migrations) and start everything again.
# After a Postgres restore, run `manage.py reconcile_graph` to bring Neo4j in line.
set -euo pipefail
cd "$(dirname "$0")/.."

kind="${1:?postgres or neo4j}"
object="${2:?object key or latest}"
target_db="${3:-}"
: "${AGE_IDENTITY_FILE:?Set AGE_IDENTITY_FILE (age private key)}"
: "${BACKUP_S3_URL:?}" "${BACKUP_S3_ACCESS_KEY:?}" "${BACKUP_S3_SECRET_KEY:?}"
BUCKET="${BACKUP_BUCKET:-andromeda-backups}"
PREFIX="${BACKUP_PREFIX:-$(hostname -s)}"

compose_args=()
for f in ${COMPOSE_FILES:-docker-compose.yml docker-compose.prod.yml}; do compose_args+=(-f "$f"); done
compose() { docker compose "${compose_args[@]}" "$@"; }

scheme="${BACKUP_S3_URL%%://*}"
export MC_HOST_backup="${scheme}://${BACKUP_S3_ACCESS_KEY}:${BACKUP_S3_SECRET_KEY}@${BACKUP_S3_URL#*://}"
tools() {
  # Runs as the invoking user, so a 0600 identity file stays readable to them only.
  compose --profile tools run --rm -T -e MC_HOST_backup --user "$(id -u):$(id -g)" \
    -v "$(realpath "$AGE_IDENTITY_FILE"):/run/age/identity:ro" backup-tools "$@"
}

if [ "$object" = latest ]; then
  object="$(tools mc ls --recursive "backup/$BUCKET/$PREFIX/$kind/" | awk '{print $NF}' | sort | tail -n 1)"
  object="$kind/$object"
  [ "$object" != "$kind/" ] || { echo "no $kind backups found" >&2; exit 1; }
fi
src="backup/$BUCKET/$PREFIX/$object"
fetch() { tools sh -c 'mc cat "$1" | age -d -i /run/age/identity' sh "$src"; }

case "$kind" in
  postgres)
    echo "restoring $src into ${target_db:-\$POSTGRES_DB}"
    fetch | compose exec -T -e TARGET_DB="$target_db" postgres sh -c \
      'pg_restore -U "$POSTGRES_USER" -d "${TARGET_DB:-$POSTGRES_DB}" --clean --if-exists --no-owner --exit-on-error'
    ;;
  neo4j)
    echo "restoring $src into neo4j (the graph is stopped meanwhile)"
    compose stop -t 120 neo4j
    fetch | compose run --rm -T --no-deps --entrypoint neo4j-admin neo4j \
      database load neo4j --from-stdin --overwrite-destination=true
    compose start neo4j
    ;;
  *)
    echo "unknown kind: $kind" >&2; exit 2 ;;
esac
echo "restore finished"
