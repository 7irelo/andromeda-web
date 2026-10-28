#!/usr/bin/env bash
# Release step: pull the tagged images and run migrations + collectstatic + deploy
# checks once, in a one-shot container, before the new version starts.
#
#   IMAGE_TAG=v1.4.0 scripts/release.sh            # then: docker compose ... up -d
#
# Migrations must be backwards compatible with the version still running
# (add columns before using them, drop them a release later), because the old
# containers keep serving until `up -d` replaces them.
set -euo pipefail
cd "$(dirname "$0")/.."

compose_args=()
for f in ${COMPOSE_FILES:-docker-compose.yml docker-compose.prod.yml}; do compose_args+=(-f "$f"); done
compose() { docker compose "${compose_args[@]}" "$@"; }

echo "release: ${IMAGE_TAG:-latest}"
compose pull --quiet --ignore-buildable
compose up -d --wait postgres redis rabbitmq neo4j minio
compose --profile release run --rm migrate
echo "release: migrations applied; start the new version with:"
echo "  docker compose ${compose_args[*]} up -d --remove-orphans"
