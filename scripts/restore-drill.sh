#!/usr/bin/env bash
# Restore drill against throwaway containers (nothing of the real stack is touched).
#
# Builds the backup-tools image, seeds a scratch Postgres and Neo4j, takes
# encrypted backups exactly the way scripts/backup.sh does (dump | age | mc pipe
# into a scratch MinIO), restores them into fresh, empty containers the way
# scripts/restore.sh does (mc cat | age -d | pg_restore / neo4j-admin load),
# and compares row and node counts plus a content checksum. Cleans up after.
#
#   scripts/restore-drill.sh
#   DRILL_NEO4J=0 scripts/restore-drill.sh     # Postgres only
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: keep container paths as written

PG_IMAGE=pgvector/pgvector:0.8.7-pg15-trixie@sha256:8d4485d6fd3156d090ac5f37eb2e22eb59d93c91169414d5809414102ee924b9
MINIO_IMAGE=pgsty/minio:RELEASE.2026-08-04T00-00-00Z@sha256:b6bfe7239bfc83fb90d31612d9704d86039dd714f7904b3f1ad68f211e602372
NEO4J_IMAGE=neo4j:5.26.31-community@sha256:c7d25c0eeebfe125718d58b72ed5d663c85d0479047733845eb2237c67ce8069
TOOLS=andromeda-backup-tools:drill
NET=andromeda-drill
P=drill
PASS="drill-$(od -An -N8 -tx8 /dev/urandom | tr -d ' ')"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NEO="${DRILL_NEO4J:-1}"

cleanup() {
  docker rm -f ${P}-pg-src ${P}-pg-dst ${P}-minio ${P}-neo-src ${P}-neo-dst >/dev/null 2>&1 || true
  docker volume rm ${P}-neo-src ${P}-neo-dst >/dev/null 2>&1 || true
  docker network rm $NET >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup
step() { echo "== $*"; }

step "build tools image"
docker build -q -t $TOOLS deploy/backup >/dev/null
docker network create $NET >/dev/null

step "start scratch Postgres (source and empty target), MinIO and Neo4j"
for name in pg-src pg-dst; do
  docker run -d --name ${P}-$name --network $NET -e POSTGRES_USER=andromeda -e POSTGRES_PASSWORD="$PASS" \
    -e POSTGRES_DB=andromeda $PG_IMAGE >/dev/null
done
docker run -d --name ${P}-minio --network $NET -e MINIO_ROOT_USER=drill -e MINIO_ROOT_PASSWORD="$PASS" \
  $MINIO_IMAGE server /data >/dev/null
if [ "$NEO" = 1 ]; then
  docker run -d --name ${P}-neo-src --network $NET -e NEO4J_AUTH="neo4j/$PASS" -v ${P}-neo-src:/data $NEO4J_IMAGE >/dev/null
fi
for name in pg-src pg-dst; do
  until docker exec ${P}-$name pg_isready -U andromeda -q 2>/dev/null; do sleep 1; done
done
if [ "$NEO" = 1 ]; then
  until docker exec ${P}-neo-src cypher-shell -u neo4j -p "$PASS" 'RETURN 1' >/dev/null 2>&1; do sleep 2; done
fi

export MC_HOST_backup="http://drill:${PASS}@${P}-minio:9000"
tools() { docker run --rm -i --network $NET --read-only --tmpfs /tmp --cap-drop ALL \
  --security-opt no-new-privileges:true -e MC_HOST_backup -e BACKUP_AGE_RECIPIENT "$@"; }
tools $TOOLS mc mb --quiet backup/andromeda-backups >/dev/null

step "generate a throwaway age key pair"
KEYDIR="$(mktemp -d)"
# Docker Desktop on Windows needs a Windows path for bind mounts.
hostpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
tools $TOOLS age-keygen 2>/dev/null > "$KEYDIR/identity"
BACKUP_AGE_RECIPIENT="$(grep -o 'age1[0-9a-z]*' "$KEYDIR/identity")"
export BACKUP_AGE_RECIPIENT

step "seed Postgres: 3 tables, 20k rows, an index, a foreign key"
docker exec -i ${P}-pg-src psql -q -v ON_ERROR_STOP=1 -U andromeda andromeda <<'SQL'
CREATE TABLE users (id bigserial PRIMARY KEY, username text UNIQUE NOT NULL, created_at timestamptz DEFAULT now());
CREATE TABLE posts (id bigserial PRIMARY KEY, author_id bigint REFERENCES users(id), content text, likes int);
CREATE TABLE likes (user_id bigint REFERENCES users(id), post_id bigint REFERENCES posts(id), PRIMARY KEY (user_id, post_id));
INSERT INTO users (username) SELECT 'user' || g FROM generate_series(1, 2000) g;
INSERT INTO posts (author_id, content, likes) SELECT 1 + (g % 2000), md5(g::text), g % 97 FROM generate_series(1, 10000) g;
INSERT INTO likes SELECT 1 + (g % 2000), 1 + (g % 10000) FROM generate_series(1, 8000) g ON CONFLICT DO NOTHING;
CREATE INDEX posts_author_idx ON posts (author_id);
SQL
pg_fingerprint() {
  docker exec ${1} psql -At -U andromeda andromeda -c \
    "SELECT (SELECT count(*) FROM users)||'/'||(SELECT count(*) FROM posts)||'/'||(SELECT count(*) FROM likes)||' '||
            (SELECT md5(string_agg(id||content||likes, ',' ORDER BY id)) FROM posts)"
}
SRC_PG="$(pg_fingerprint ${P}-pg-src)"

SRC_NEO=skipped DST_NEO=skipped NEO_SECONDS=0
if [ "$NEO" = 1 ]; then
step "seed Neo4j: 500 users, 499 friendships, 300 posts"
docker exec ${P}-neo-src cypher-shell -u neo4j -p "$PASS" \
  "UNWIND range(1,500) AS i CREATE (:UserNode {user_id: i, username: 'user'+i})
   WITH count(*) AS users MATCH (a:UserNode), (b:UserNode) WHERE b.user_id = a.user_id + 1 CREATE (a)-[:FRIEND_WITH]->(b)
   WITH count(*) AS links UNWIND range(1,300) AS p CREATE (:PostNode {post_id: p})" >/dev/null
neo_fingerprint() {
  docker exec ${1} cypher-shell -u neo4j -p "$PASS" --format plain \
    "MATCH (n) WITH count(n) AS nodes MATCH ()-[r]->() RETURN nodes, count(r)" | tail -n 1
}
SRC_NEO="$(neo_fingerprint ${P}-neo-src)"
fi

step "backup Postgres: pg_dump -Fc | age | mc pipe"
docker exec ${P}-pg-src pg_dump -U andromeda -d andromeda -Fc --no-owner \
  | tools $TOOLS sh -c 'age -r "$BACKUP_AGE_RECIPIENT" | mc pipe --quiet "backup/andromeda-backups/drill/postgres/'"$STAMP"'.dump.age"'

if [ "$NEO" = 1 ]; then
step "backup Neo4j (stopped): neo4j-admin dump | age | mc pipe"
docker stop -t 120 ${P}-neo-src >/dev/null   # clean shutdown: dump refuses an active log
docker run --rm -v ${P}-neo-src:/data --entrypoint neo4j-admin $NEO4J_IMAGE database dump neo4j --to-stdout 2>/dev/null \
  | tools $TOOLS sh -c 'age -r "$BACKUP_AGE_RECIPIENT" | mc pipe --quiet "backup/andromeda-backups/drill/neo4j/'"$STAMP"'.dump.age"'
fi

step "what's in the bucket (and proof it's encrypted)"
tools $TOOLS mc ls --recursive backup/andromeda-backups/drill/
tools $TOOLS sh -c 'mc cat "backup/andromeda-backups/drill/postgres/'"$STAMP"'.dump.age" | head -c 21'; echo

step "restore Postgres into the empty target: mc cat | age -d | pg_restore"
started=$(date +%s)
tools --user "$(id -u):$(id -g)" -v "$(hostpath "$KEYDIR/identity"):/run/age/identity:ro" $TOOLS sh -c \
  'mc cat "backup/andromeda-backups/drill/postgres/'"$STAMP"'.dump.age" | age -d -i /run/age/identity' \
  | docker exec -i ${P}-pg-dst pg_restore -U andromeda -d andromeda --clean --if-exists --no-owner --exit-on-error
PG_SECONDS=$(( $(date +%s) - started ))
DST_PG="$(pg_fingerprint ${P}-pg-dst)"

if [ "$NEO" = 1 ]; then
step "restore Neo4j into an empty volume: mc cat | age -d | neo4j-admin load"
started=$(date +%s)
tools --user "$(id -u):$(id -g)" -v "$(hostpath "$KEYDIR/identity"):/run/age/identity:ro" $TOOLS sh -c \
  'mc cat "backup/andromeda-backups/drill/neo4j/'"$STAMP"'.dump.age" | age -d -i /run/age/identity' \
  | docker run --rm -i -v ${P}-neo-dst:/data --entrypoint neo4j-admin $NEO4J_IMAGE \
      database load neo4j --from-stdin --overwrite-destination=true 2>/dev/null
docker run -d --name ${P}-neo-dst --network $NET -e NEO4J_AUTH="neo4j/$PASS" -v ${P}-neo-dst:/data $NEO4J_IMAGE >/dev/null
until docker exec ${P}-neo-dst cypher-shell -u neo4j -p "$PASS" 'RETURN 1' >/dev/null 2>&1; do sleep 2; done
NEO_SECONDS=$(( $(date +%s) - started ))
DST_NEO="$(neo_fingerprint ${P}-neo-dst)"
fi
rm -rf "$KEYDIR"

echo
echo "postgres  source:   $SRC_PG"
echo "postgres  restored: $DST_PG   (${PG_SECONDS}s)"
echo "neo4j     source:   $SRC_NEO"
echo "neo4j     restored: $DST_NEO   (${NEO_SECONDS}s incl. start-up)"
if [ "$SRC_PG" = "$DST_PG" ] && [ "$SRC_NEO" = "$DST_NEO" ]; then
  echo "RESTORE DRILL PASSED"
else
  echo "RESTORE DRILL FAILED" >&2
  exit 1
fi
