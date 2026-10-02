# Secret containers only. Values are added by scripts/set-secrets.sh, which prompts for them
# or generates them, so no secret is ever in Terraform state or this repo.
locals {
  api_secrets = {
    API_DATABASE_URL     = "api-database-url"
    SECRET_KEY           = "secret-key"
    TURNSTILE_SECRET_KEY = "turnstile-secret-key"
    RESEND_API_KEY       = "resend-api-key"
  }
  push_secrets = var.vapid_public_key == "" ? {} : { VAPID_PRIVATE_KEY = "vapid-private-key" }
  job_secrets  = { DATABASE_URL = "database-url" }
  all_secrets  = merge(local.api_secrets, local.job_secrets, { VAPID_PRIVATE_KEY = "vapid-private-key" })
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
  for_each  = merge(local.api_secrets, local.push_secrets)
  secret_id = google_secret_manager_secret.app[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "ops_reads" {
  for_each  = merge(local.api_secrets, local.job_secrets)
  secret_id = google_secret_manager_secret.app[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ops.email}"
}
