# ── Stage 1: Build ─────────────────────────────────────────────────────────────
FROM node:24-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci --legacy-peer-deps

COPY . .
# Optional browser error reporting: a Sentry DSN baked into the bundle (it is public by design).
ARG SENTRY_FRONTEND_DSN=""
RUN if [ -n "$SENTRY_FRONTEND_DSN" ]; then \
      echo "$SENTRY_FRONTEND_DSN" | grep -Eq '^https://[A-Za-z0-9]+@[A-Za-z0-9.-]+/[0-9]+$' \
        || { echo 'SENTRY_FRONTEND_DSN is not a Sentry DSN' >&2; exit 1; }; \
      sed -i "s|sentryDsn: ''|sentryDsn: '$SENTRY_FRONTEND_DSN'|" src/environments/environment.prod.ts; \
    fi
RUN npm run build -- --configuration=production

# ── Stage 2: Serve with Nginx ──────────────────────────────────────────────────
FROM nginx:1.27-alpine

COPY --from=builder /app/dist/andromeda/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s \
    CMD wget -q --spider http://127.0.0.1/ || exit 1
