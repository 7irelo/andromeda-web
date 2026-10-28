#!/usr/bin/env bash
# Seed a NON-PRODUCTION stack for the k6 scripts and print the chat room id.
#
#   loadtest/seed.sh [users] [room_members]
#
# Uses the dev compose stack (docker compose up -d). Every seeded account
# (demo0..demoN-1) shares one password, so never point this at production.
set -euo pipefail
cd "$(dirname "$0")/.."
users="${1:-200}"
members="${2:-100}"

docker compose exec -T django python manage.py seed --users "$users" --i-know-this-is-not-production
docker compose exec -T django python manage.py seed_loadtest --members "$members" --i-know-this-is-not-production \
  | tail -n 1 > loadtest/.fixtures.json
echo "fixtures: $(cat loadtest/.fixtures.json | head -c 200)..."
echo "ROOM_ID=$(sed -E 's/.*"room_id": ([0-9]+).*/\1/' loadtest/.fixtures.json)"
