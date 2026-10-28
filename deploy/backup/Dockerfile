# Backup/restore tools: pg_dump/pg_restore from the same Postgres 15 build as
# the database, age for encryption and the MinIO client for S3 uploads.
# Used by scripts/backup.sh, scripts/restore.sh and scripts/restore-drill.sh.
FROM pgsty/mc:RELEASE.2026-09-16T00-00-00Z@sha256:cfc83108c3abb371f8fb84d99c1fdc88f8c237e022409b0081fb7c0a3be634dd AS mc

FROM pgvector/pgvector:0.8.7-pg15-trixie@sha256:8d4485d6fd3156d090ac5f37eb2e22eb59d93c91169414d5809414102ee924b9

RUN apt-get update \
    && apt-get install -y --no-install-recommends age ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=mc /usr/bin/mc /usr/local/bin/mc

# mc keeps its config in $HOME; the container runs read-only with /tmp as tmpfs.
# Aliases come from MC_HOST_<alias> env vars, so nothing is written there.
ENV HOME=/tmp MC_CONFIG_DIR=/tmp/.mc
USER 10003:10003
ENTRYPOINT []
CMD ["sh"]
