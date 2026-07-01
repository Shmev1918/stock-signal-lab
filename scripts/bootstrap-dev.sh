#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[bootstrap] %s\n' "$*"
}

die() {
  printf '[bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

ensure_env_file() {
  if [[ ! -f .env ]]; then
    log "Creating .env from .env.example"
    cp .env.example .env
  fi

  if grep -qE '^MARKET_DATA_PROVIDER=' .env; then
    return
  fi

  log "Defaulting MARKET_DATA_PROVIDER=mock in .env"
  printf '\nMARKET_DATA_PROVIDER=mock\n' >> .env
}

main() {
  local script_dir repo_root
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd "$script_dir/.." && pwd)"
  cd "$repo_root"

  need_cmd docker

  if ! docker compose version >/dev/null 2>&1; then
    die "docker compose is not working"
  fi

  ensure_env_file

  log "Starting local services"
  docker compose up -d --build

  log "Applying database migrations"
  docker compose run --rm app alembic upgrade head

  cat <<'EOF'

Local app is ready.

Backend: http://localhost:8000
Health:  http://localhost:8000/health/details
Frontend: http://localhost:5173

Next commands:
  make refresh
  make rankings
  make status
EOF
}

main "$@"
