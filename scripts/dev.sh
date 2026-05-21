#!/usr/bin/env bash
# Go4Ride local dev helper — always uses the project .venv (Python 3.11+).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_MIN=311

need_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3.11+ (e.g. brew install python@3.12)."
    exit 1
  fi
  local ver
  ver="$(python3 -c 'import sys; print(f"{sys.version_info.major}{sys.version_info.minor:02d}")')"
  if [[ "$ver" -lt "$PYTHON_MIN" ]]; then
    echo "ERROR: Need Python 3.11+, found $(python3 --version)."
    echo "       Deactivate conda (conda deactivate) and use Homebrew/python.org 3.11+."
    exit 1
  fi
}

ensure_venv() {
  need_python
  if [[ ! -d .venv ]]; then
    echo "Creating .venv with $(python3 --version)..."
    python3 -m venv .venv
  fi
  # shellcheck source=/dev/null
  source .venv/bin/activate
  if [[ "$(python -c 'import sys; print(sys.version_info.minor)')" -lt 11 ]]; then
    echo "ERROR: .venv has $(python --version). Remove it and re-run: rm -rf .venv"
    exit 1
  fi
  pip install -q -e ".[dev]"
}

check_docker() {
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker is not running."
    echo "       Open Docker Desktop (or start the Docker daemon), then run:"
    echo "         docker compose up -d"
    exit 1
  fi
}

wait_postgres() {
  echo "Waiting for Postgres (Docker on localhost:5433)..."
  local i
  for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U go4ride -d go4ride >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "ERROR: Postgres container did not become ready."
  exit 1
}

ensure_env_db_port() {
  if [[ -f .env ]] && grep -q '@localhost:5432/' .env 2>/dev/null; then
    echo "Updating .env: Postgres URL port 5432 -> 5433 (Docker; avoids local Postgres conflict)."
    sed -i '' 's|@localhost:5432/|@localhost:5433/|g' .env
  fi
}

cmd="${1:-help}"

case "$cmd" in
  setup)
    ensure_venv
    [[ -f .env ]] || cp .env.example .env
    ensure_env_db_port
    check_docker
    docker compose up -d
    wait_postgres
    alembic upgrade head
    python -m app.db.seed
    echo ""
    echo "Setup complete. Start the API:"
    echo "  ./scripts/dev.sh run"
    ;;
  run)
    ensure_venv
    [[ -f .env ]] || cp .env.example .env
    exec uvicorn app.main:app --reload --port 8000
    ;;
  demo)
    ensure_venv
    python scripts/phase1_demo.py
    ;;
  migrate)
    ensure_venv
    ensure_env_db_port
    check_docker
    wait_postgres
    alembic upgrade head
    ;;
  seed)
    ensure_venv
    python -m app.db.seed
    ;;
  reset-db)
    check_docker
    echo "Stopping containers and removing Postgres volume..."
    docker compose down -v
    docker compose up -d
    wait_postgres
    ensure_venv
    ensure_env_db_port
    alembic upgrade head
    python -m app.db.seed
    echo "Database reset complete."
    ;;
  help|*)
    cat <<EOF
Usage: ./scripts/dev.sh <command>

Commands:
  setup    Create .venv, install deps, start Docker, migrate, seed
  run      Start uvicorn (port 8000)
  demo     Run scripts/phase1_demo.py
  migrate   alembic upgrade head
  seed      python -m app.db.seed
  reset-db  Wipe Postgres volume and re-migrate + seed

Important:
  - Do NOT use conda env "mlp" (Python 3.8). This project needs Python 3.11+.
  - Run: conda deactivate   then use this script (it activates .venv for you).
  - Docker Desktop must be running before setup/migrate.
EOF
    ;;
esac
