#!/usr/bin/env bash
# Puts the production secrets into Secret Manager (ADR-032, ADR-042). Prompts for the ones that
# come from accounts (input is not echoed) and generates the rest. Nothing is printed or written
# to disk. Run after `terraform apply` has created the secret containers:
#   infra/scripts/set-secrets.sh <project-id>          the first set (Phase 1)
#   infra/scripts/set-secrets.sh <project-id> phase2   only Phase 2's; Enter skips any of them
# Re-running adds new versions; Cloud Run picks them up on the next deploy. Re-running the first
# set makes a new SECRET_KEY, which signs everyone out and breaks unsubscribe links: use phase2
# to add the newer secrets.
set -euo pipefail

project="${1:?usage: set-secrets.sh <project-id> [phase2]}"
mode="${2:-base}"

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

# Like ask, but Enter skips (prints nothing).
maybe() {
  local value
  read -rsp "$1 (Enter to skip): " value
  echo >&2
  printf '%s' "$value"
}

has_version() {
  [ -n "$(gcloud secrets versions list "$1" --project="$project" --filter=state=ENABLED \
    --limit=1 --format='value(name)' 2>/dev/null)" ]
}

if [ "$mode" = "phase2" ]; then
  # Made once: a new key would leave every tenant's stored credentials unreadable.
  if has_version integrations-key; then
    echo "  integrations-key already set; kept (a new one would disconnect every integration)"
  else
    put integrations-key "$(openssl rand -base64 32 | tr -d '\n')"
  fi

  echo "Paste with right-click or Shift+Insert: in Git Bash, Ctrl+V types a control character."
  echo "Anthropic: platform.claude.com -> API Keys -> Create key (e.g. cornerpin-production)."
  value="$(maybe 'Anthropic API key')"
  if [ -n "$value" ]; then
    case "$value" in sk-ant-*) ;; *) echo "that isn't an Anthropic key (sk-ant-...)" >&2; exit 1 ;; esac
    put anthropic-api-key "$value"
    echo "    then: agent_enabled = true"
  fi

  echo "Resend: replies are fetched with the API key, so it needs Full access, not sending only."
  value="$(maybe 'A new Resend API key, Full access (re_...; Enter keeps the current one)')"
  if [ -n "$value" ]; then
    case "$value" in re_*) ;; *) echo "that isn't a Resend key (re_...)" >&2; exit 1 ;; esac
    put resend-api-key "$value"
  fi

  echo "Resend: Webhooks -> the cornerpin.app/v1/webhooks/resend endpoint -> Signing secret."
  value="$(maybe 'Resend webhook signing secret (whsec_...)')"
  if [ -n "$value" ]; then
    case "$value" in whsec_*) ;; *) echo "that isn't a whsec_ secret" >&2; exit 1 ;; esac
    put resend-webhook-secret "$value"
    echo "    then: inbound_email_domain = \"reply.cornerpin.app\""
  fi

  echo "Slack: api.slack.com/apps -> Cornerpin -> Basic Information -> App Credentials."
  client_secret="$(maybe 'Slack Client Secret')"
  if [ -n "$client_secret" ]; then
    put slack-client-secret "$client_secret"
    put slack-signing-secret "$(ask 'Slack Signing Secret')"
    echo "    then: slack_client_id = \"<the app's Client ID>\""
  fi
  echo "Done. Turn on what you set in terraform.tfvars, terraform apply, then deploy."
  exit 0
fi

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
# Full access: Phase 2 fetches buyers' replies with it; a sending-only key gets a 401.
put resend-api-key "$(ask 'Resend API key (Full access)')"

read -rp "Turn on web push now? Generates a key pair. [y/N] " push
if [[ "$push" =~ ^[Yy]$ ]]; then
  keys="$(cd "$(dirname "$0")/../.." && uv run python -m cornerpin.devtools vapid-keys)"
  put vapid-private-key "$(grep '^VAPID_PRIVATE_KEY=' <<<"$keys" | cut -d= -f2-)"
  echo "  Public key for terraform.tfvars (vapid_public_key):"
  grep '^VAPID_PUBLIC_KEY=' <<<"$keys" | cut -d= -f2-
fi

echo "Done. The next deploy's migrate job gives cornerpin_api its new password."
