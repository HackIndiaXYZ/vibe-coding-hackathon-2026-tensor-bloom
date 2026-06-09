#!/usr/bin/env bash
# Cosign — generate local dev secrets: JWT RS256 keypair + AES-GCM key.
# Idempotent: skips anything that already exists. Never commit infra/secrets/.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="$REPO_ROOT/infra/secrets"
ENV_FILE="$REPO_ROOT/infra/.env"
mkdir -p "$SECRETS_DIR"

log() { printf '\033[1;36m[keys]\033[0m %s\n' "$*"; }

command -v openssl >/dev/null 2>&1 || { log "openssl not found — skipping key generation"; exit 0; }

# ── JWT RS256 keypair ─────────────────────────────────────────────────────────
if [[ ! -f "$SECRETS_DIR/jwt_private.pem" ]]; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    -out "$SECRETS_DIR/jwt_private.pem" 2>/dev/null
  openssl rsa -pubout -in "$SECRETS_DIR/jwt_private.pem" \
    -out "$SECRETS_DIR/jwt_public.pem" 2>/dev/null
  # World-readable: the distroless nonroot api container (uid 65532) mounts these.
  # Dev keys only — never reuse in production.
  chmod 644 "$SECRETS_DIR/jwt_private.pem" "$SECRETS_DIR/jwt_public.pem"
  log "generated JWT RS256 keypair"
fi

# ── AES-GCM key for OAuth-token-at-rest (32 bytes, base64) ─────────────────────
# Matches an empty value, optionally followed by whitespace/comment.
if [[ -f "$ENV_FILE" ]] && grep -qE '^OAUTH_TOKEN_ENCRYPTION_KEY=[[:space:]]*(#.*)?$' "$ENV_FILE"; then
  KEY="$(openssl rand -base64 32)"
  tmp="$(mktemp)"
  sed -E "s|^OAUTH_TOKEN_ENCRYPTION_KEY=[[:space:]]*(#.*)?\$|OAUTH_TOKEN_ENCRYPTION_KEY=${KEY//|/\\|}|" "$ENV_FILE" > "$tmp"
  mv "$tmp" "$ENV_FILE"
  log "set OAUTH_TOKEN_ENCRYPTION_KEY in .env"
fi

log "secrets ready in infra/secrets/ (gitignored)"
