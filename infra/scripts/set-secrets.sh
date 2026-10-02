#!/usr/bin/env bash
# Puts the production secrets into Secret Manager (ADR-032). Prompts for the ones that come
# from accounts (input is not echoed) and generates the rest. Nothing is printed or written to
# disk. Run after `terraform apply` has created the secret containers:
#   infra/scripts/set-secrets.sh <project-id>
# Re-running adds new versions; Cloud Run picks them up on the next deploy.
set -euo pipefail

project="${1:?usage: set-secrets.sh <project-id>}"

put() {
  printf '%s' "$2" | gcloud secrets versions add "$1" --project="$project" --data-file=- >/dev/null
  echo "  set $1"
}

ask() {
  local value
  read -rsp "$1: " value
  echo >&2
  [ -n "$value" ] || { echo "nothing entered; stopping" >&2; exit 1; }
  printf '%s' "$value"
}

echo "Neon: Dashboard -> Connect -> 'Connection string', with 'Connection pooling' OFF (the"
echo "direct endpoint, not -pooler), role neondb_owner. It looks like"
echo "  postgresql://neondb_owner:...@ep-....us-west-2.aws.neon.tech/neondb?sslmode=require"
neon="$(ask 'Neon owner connection string')"
case "$neon" in
  postgresql://*|postgres://*) ;;
  *) echo "that doesn't look like a postgresql:// URL" >&2; exit 1 ;;
esac
owner_url="postgresql+psycopg://${neon#*://}"
# Same host and database, as the API's own non-owner role with a fresh password.
api_password="$(openssl rand -hex 24)"
after_at="${neon#*@}"
api_url="postgresql+psycopg://cornerpin_api:${api_password}@${after_at}"

put database-url "$owner_url"
put api-database-url "$api_url"
put secret-key "$(openssl rand -base64 48 | tr -d '\n')"
put turnstile-secret-key "$(ask 'Cloudflare Turnstile secret key for cornerpin.app')"
put resend-api-key "$(ask 'Resend API key (sending access)')"

read -rp "Turn on web push now? Generates a key pair. [y/N] " push
if [[ "$push" =~ ^[Yy]$ ]]; then
  keys="$(cd "$(dirname "$0")/../.." && uv run python -m cornerpin.devtools vapid-keys)"
  put vapid-private-key "$(grep '^VAPID_PRIVATE_KEY=' <<<"$keys" | cut -d= -f2-)"
  echo "  Public key for terraform.tfvars (vapid_public_key):"
  grep '^VAPID_PUBLIC_KEY=' <<<"$keys" | cut -d= -f2-
fi

echo "Done. The next deploy's migrate job gives cornerpin_api its new password."
