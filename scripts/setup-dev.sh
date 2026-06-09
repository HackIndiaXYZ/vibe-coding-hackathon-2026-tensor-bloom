#!/usr/bin/env bash
# Cosign — one-command local bootstrap (WORKSTREAMS WS4 §5).
# Brings up Postgres + Redis, applies migrations, builds the sandbox image.
# App services (api/worker/web) start via `--with-app` once their Dockerfiles land.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$REPO_ROOT/infra"
cd "$INFRA_DIR"

log()  { printf '\033[1;36m[setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

WITH_APP=0
[[ "${1:-}" == "--with-app" ]] && WITH_APP=1

# ── 1. dependency checks ──────────────────────────────────────────────────────
log "checking dependencies..."
for bin in docker; do
  command -v "$bin" >/dev/null 2>&1 || die "missing dependency: $bin"
done
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"

# ── 2. .env ───────────────────────────────────────────────────────────────────
if [[ ! -f "$INFRA_DIR/.env" ]]; then
  cp "$INFRA_DIR/.env.example" "$INFRA_DIR/.env"
  warn ".env created from .env.example — fill in GitHub + LLM keys before running app services."
fi

# ── 3. dev secrets (JWT keypair + AES key) ────────────────────────────────────
"$REPO_ROOT/scripts/gen-keys.sh" || warn "key generation skipped"

# ── 4. sandbox image ──────────────────────────────────────────────────────────
log "building sandbox image (cosign/sandbox:latest)..."
docker build -f "$INFRA_DIR/sandbox.Dockerfile" -t cosign/sandbox:latest "$INFRA_DIR" >/dev/null
docker network inspect cosign_sandbox_net >/dev/null 2>&1 || \
  docker network create cosign_sandbox_net >/dev/null

# ── 5. data stores ────────────────────────────────────────────────────────────
log "starting postgres + redis..."
docker compose up -d postgres redis

log "waiting for healthchecks..."
for svc in postgres redis; do
  for i in $(seq 1 30); do
    status="$(docker compose ps --format '{{.Health}}' "$svc" 2>/dev/null || true)"
    [[ "$status" == "healthy" ]] && { log "$svc healthy"; break; }
    [[ $i -eq 30 ]] && die "$svc did not become healthy in time"
    sleep 2
  done
done

# ── 6. migrations (idempotent — tracked in schema_migrations) ─────────────────
log "applying migrations..."
psql_cmd() { docker compose exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "${POSTGRES_USER:-cosign}" -d "${POSTGRES_DB:-cosign}" "$@"; }

psql_cmd -c "CREATE TABLE IF NOT EXISTS schema_migrations (
  filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW());" >/dev/null

# Backfill: if the core schema already exists but isn't recorded, mark 0001 applied
# so a pre-migration-ledger database doesn't try to re-create existing tables.
if psql_cmd -tAc "SELECT to_regclass('public.users') IS NOT NULL" | grep -q t; then
  psql_cmd -c "INSERT INTO schema_migrations (filename) VALUES ('0001_init.sql')
               ON CONFLICT DO NOTHING;" >/dev/null
fi

for f in "$INFRA_DIR"/postgres/migrations/*.sql; do
  [[ -e "$f" ]] || continue
  name="$(basename "$f")"
  if psql_cmd -tAc "SELECT 1 FROM schema_migrations WHERE filename='$name'" | grep -q 1; then
    log "  -> $name (already applied)"
    continue
  fi
  log "  -> $name"
  psql_cmd < "$f"
  psql_cmd -c "INSERT INTO schema_migrations (filename) VALUES ('$name') ON CONFLICT DO NOTHING;" >/dev/null
done

# ── 7. app services (optional) ────────────────────────────────────────────────
if [[ "$WITH_APP" == "1" ]]; then
  log "building + starting app services..."
  docker compose --profile app up -d --build
fi

log "Cosign data stores are up."
[[ "$WITH_APP" == "1" ]] && log "App is up at http://localhost:3000" \
                          || log "Run with --with-app once service Dockerfiles exist."
