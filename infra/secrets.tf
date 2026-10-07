# Secret containers only. Values are added by scripts/set-secrets.sh, which prompts for them
# or generates them, so no secret is ever in Terraform state or this repo.
#
# Cloud Run won't start a revision that names a secret with no version, so a feature's secrets
# are wired to the API only once its switch in terraform.tfvars is on (ADR-042). The containers
# always exist, so set-secrets.sh can fill them first.
locals {
  api_secrets = {
    API_DATABASE_URL     = "api-database-url"
    SECRET_KEY           = "secret-key"
    TURNSTILE_SECRET_KEY = "turnstile-secret-key"
    RESEND_API_KEY       = "resend-api-key"
    INTEGRATIONS_KEY     = "integrations-key" # seals tenants' Slack and Salesforce credentials
  }
  push_secrets  = var.vapid_public_key == "" ? {} : { VAPID_PRIVATE_KEY = "vapid-private-key" }
  agent_secrets = var.agent_enabled ? { ANTHROPIC_API_KEY = "anthropic-api-key" } : {}
  inbound_secrets = var.inbound_email_domain == "" ? {} : {
    RESEND_WEBHOOK_SECRET = "resend-webhook-secret"
  }
  slack_secrets = var.slack_client_id == "" ? {} : {
    SLACK_CLIENT_SECRET  = "slack-client-secret"
    SLACK_SIGNING_SECRET = "slack-signing-secret"
  }
  optional_secrets = merge(local.push_secrets, local.agent_secrets, local.inbound_secrets, local.slack_secrets)
  job_secrets      = { DATABASE_URL = "database-url" }
  all_secrets = merge(local.api_secrets, local.job_secrets, {
    VAPID_PRIVATE_KEY     = "vapid-private-key"
    ANTHROPIC_API_KEY     = "anthropic-api-key"
    RESEND_WEBHOOK_SECRET = "resend-webhook-secret"
    SLACK_CLIENT_SECRET   = "slack-client-secret"
    SLACK_SIGNING_SECRET  = "slack-signing-secret"
  })
}

resource "google_secret_manager_secret" "app" {
  for_each  = local.all_secrets
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled]
}

# The running API reads its own secrets but never the owner's database URL; only the jobs
# (migrations, seeding, creating tenants) do.
resource "google_secret_manager_secret_iam_member" "api_reads" {
  for_each  = merge(local.api_secrets, local.optional_secrets)
  secret_id = google_secret_manager_secret.app[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "ops_reads" {
  for_each  = merge(local.api_secrets, local.optional_secrets, local.job_secrets)
  secret_id = google_secret_manager_secret.app[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ops.email}"
}
