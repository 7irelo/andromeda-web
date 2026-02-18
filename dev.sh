#!/usr/bin/env bash
# =============================================================================
# Andromeda – Local Development Launcher
# Starts infrastructure via Docker, then runs the Django backend, Celery
# worker + beat, and Angular dev server as native processes.
#
# Usage:  bash dev.sh [--no-client] [--no-celery] [--reset-db]
#
# Requirements: Docker, Python 3.11+, Node 18+
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$ROOT/server"
CLIENT_DIR="$ROOT/client"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()    { echo -e "${CYAN}[andromeda]${NC} $*"; }
ok()     { echo -e "${GREEN}[andromeda]${NC} $*"; }
warn()   { echo -e "${YELLOW}[andromeda]${NC} $*"; }
die()    { echo -e "${RED}[andromeda] ERROR:${NC} $*" >&2; exit 1; }

# ── Flags ────────────────────────────────────────────────────────────────────
RUN_CLIENT=true
RUN_CELERY=true
RESET_DB=false

for arg in "$@"; do
  case $arg in
    --no-client) RUN_CLIENT=false ;;
    --no-celery) RUN_CELERY=false ;;
    --reset-db)  RESET_DB=true ;;
    -h|--help)
      echo "Usage: bash dev.sh [--no-client] [--no-celery] [--reset-db]"
      exit 0 ;;
  esac
done

# ── Track background PIDs for cleanup ────────────────────────────────────────
PIDS=()

cleanup() {
  echo ""
  warn "Shutting down background processes..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  log "Stopping Docker infrastructure..."
  docker compose -f "$ROOT/docker-compose.yml" stop postgres redis rabbitmq neo4j 2>/dev/null || true
  ok "Done. Goodbye!"
}
trap cleanup SIGINT SIGTERM EXIT

# ── 1. Prerequisite checks ────────────────────────────────────────────────────
log "Checking prerequisites..."

command -v docker >/dev/null 2>&1 || die "Docker is not installed or not in PATH."
docker info >/dev/null 2>&1       || die "Docker daemon is not running."

command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 \
  || die "Python 3 is not installed."
PYTHON=$(command -v python3 2>/dev/null || command -v python)

if $RUN_CLIENT; then
  command -v node >/dev/null 2>&1 || die "Node.js is not installed."
  command -v npm  >/dev/null 2>&1 || die "npm is not installed."
fi

ok "Prerequisites OK."

# ── 2. .env setup ────────────────────────────────────────────────────────────
if [[ ! -f "$ROOT/.env" ]]; then
  warn ".env not found – copying from .env.example"
  cp "$ROOT/.env.example" "$ROOT/.env"
  warn "Review $ROOT/.env and set any required secrets, then re-run."
fi

# Local-dev env overrides (services running on localhost, not Docker hostnames)
export DEBUG=True
export POSTGRES_HOST=localhost
export POSTGRES_DB="${POSTGRES_DB:-andromeda}"
export POSTGRES_USER="${POSTGRES_USER:-andromeda}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-andromeda_secret}"
export NEO4J_BOLT_URL="bolt://neo4j:${NEO4J_PASSWORD:-andromeda_secret}@localhost:7687"
export REDIS_URL="redis://:${REDIS_PASSWORD:-redis_secret}@localhost:6379/0"
export RABBITMQ_URL="amqp://${RABBITMQ_USER:-andromeda}:${RABBITMQ_PASSWORD:-andromeda_secret}@localhost:5672/andromeda"
export SECRET_KEY="${SECRET_KEY:-django-insecure-local-dev-only}"
export ALLOWED_HOSTS="localhost,127.0.0.1"
export CORS_ALLOWED_ORIGINS="http://localhost:4200,http://127.0.0.1:4200"

# ── 3. Start infrastructure containers ───────────────────────────────────────
log "Starting infrastructure (postgres, redis, rabbitmq, neo4j)..."
docker compose -f "$ROOT/docker-compose.yml" up -d postgres redis rabbitmq neo4j

# ── 4. Wait for healthy services ──────────────────────────────────────────────
wait_healthy() {
  local service="$1" max="${2:-60}" elapsed=0
  log "Waiting for $service to be healthy..."
  until docker compose -f "$ROOT/docker-compose.yml" ps "$service" \
        | grep -q "healthy"; do
    sleep 2; elapsed=$((elapsed + 2))
    if [[ $elapsed -ge $max ]]; then
      die "$service did not become healthy within ${max}s."
    fi
    echo -n "."
  done
  echo ""
  ok "$service is healthy."
}

wait_healthy postgres 90
wait_healthy redis    60
wait_healthy rabbitmq 90
# Neo4j takes longer on first boot (APOC download)
wait_healthy neo4j    180

# ── 5. Python virtual environment ────────────────────────────────────────────
# Prefer existing Tempandromeda_venv, otherwise use .venv
if [[ -d "$ROOT/Tempandromeda_venv" ]]; then
  VENV_DIR="$ROOT/Tempandromeda_venv"
elif [[ -d "$ROOT/.venv" ]]; then
  VENV_DIR="$ROOT/.venv"
else
  VENV_DIR="$ROOT/.venv"
  log "Creating virtual environment at $VENV_DIR ..."
  "$PYTHON" -m venv "$VENV_DIR"
fi

# Activate (Git Bash on Windows uses Scripts/, Unix uses bin/)
if [[ -f "$VENV_DIR/Scripts/activate" ]]; then
  # shellcheck disable=SC1091
  source "$VENV_DIR/Scripts/activate"
else
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
fi
ok "Virtual environment activated."

# ── 6. Install Python dependencies ───────────────────────────────────────────
log "Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r "$SERVER_DIR/requirements.txt"
ok "Python dependencies installed."

# ── 7. Node dependencies ──────────────────────────────────────────────────────
if $RUN_CLIENT && [[ ! -d "$CLIENT_DIR/node_modules" ]]; then
  log "Installing Node dependencies (this may take a minute)..."
  npm --prefix "$CLIENT_DIR" ci
  ok "Node dependencies installed."
fi

# ── 8. Reset DB if requested ─────────────────────────────────────────────────
if $RESET_DB; then
  warn "--reset-db: dropping and re-creating the postgres database..."
  docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
    psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS $POSTGRES_DB;" 2>/dev/null || true
  docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
    psql -U "$POSTGRES_USER" -c "CREATE DATABASE $POSTGRES_DB;" 2>/dev/null || true
fi

# ── 9. Django migrations ──────────────────────────────────────────────────────
log "Running Django migrations..."
cd "$SERVER_DIR"
python manage.py migrate --noinput
ok "Migrations applied."

# ── 10. Django dev server (uvicorn ASGI) ──────────────────────────────────────
log "Starting Django ASGI server on http://localhost:8000 ..."
uvicorn andromeda.asgi:application \
  --host 127.0.0.1 \
  --port 8000 \
  --reload \
  --reload-dir "$SERVER_DIR" \
  --log-level info &
PIDS+=($!)
ok "Django running (PID ${PIDS[-1]})."

# ── 11. Celery worker + beat ──────────────────────────────────────────────────
if $RUN_CELERY; then
  log "Starting Celery worker..."
  celery -A andromeda worker \
    --loglevel=info \
    --concurrency=2 \
    -Q notifications,messages,default \
    --logfile="$ROOT/celery-worker.log" &
  PIDS+=($!)
  ok "Celery worker running (PID ${PIDS[-1]}). Logs → celery-worker.log"

  log "Starting Celery beat..."
  celery -A andromeda beat \
    --loglevel=info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler \
    --logfile="$ROOT/celery-beat.log" &
  PIDS+=($!)
  ok "Celery beat running (PID ${PIDS[-1]}). Logs → celery-beat.log"
fi

# ── 12. Angular dev server ────────────────────────────────────────────────────
if $RUN_CLIENT; then
  log "Starting Angular dev server on http://localhost:4200 ..."
  cd "$CLIENT_DIR"
  npm start &
  PIDS+=($!)
  ok "Angular running (PID ${PIDS[-1]})."
fi

# ── 13. Summary ───────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        Andromeda is running locally          ║${NC}"
echo -e "${BOLD}╠══════════════════════════════════════════════╣${NC}"
echo -e "${BOLD}║${NC}  App          →  ${GREEN}http://localhost:4200${NC}       ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}  API          →  ${GREEN}http://localhost:8000/api${NC}   ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}  Admin        →  ${GREEN}http://localhost:8000/admin${NC} ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}  RabbitMQ UI  →  ${GREEN}http://localhost:15672${NC}      ${BOLD}║${NC}"
echo -e "${BOLD}║${NC}  Neo4j UI     →  ${GREEN}http://localhost:7474${NC}       ${BOLD}║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop everything."
echo ""

# Keep script alive waiting for background jobs
wait
