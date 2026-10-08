# Cloud Run services and jobs (ADR-032). Terraform owns their shape; the deploy workflow owns
# which image runs, so image changes are ignored here.

locals {
  api_env = {
    ENVIRONMENT           = "production"
    WEB_ORIGIN            = local.site
    TURNSTILE_SITE_KEY    = var.turnstile_site_key
    EMAIL_BACKEND         = "resend"
    EMAIL_FROM            = var.email_from
    STORAGE_BACKEND       = "gcs"
    STORAGE_BUCKET        = google_storage_bucket.uploads.name
    OUTBOX_RUNNER         = "cloudtasks"
    CLOUD_TASKS_QUEUE     = google_cloud_tasks_queue.outbox.id
    INTERNAL_BASE_URL     = local.api_url
    TASKS_SERVICE_ACCOUNT = google_service_account.tasks.email
    VAPID_PUBLIC_KEY      = var.vapid_public_key
    # The lead model lives in its own service (ADR-048); the API image has none.
    DECISIONING_URL = local.decisioning_url
    # Phase 2 (ADR-042): each stays dormant while its terraform.tfvars switch is off.
    AGENT_MODEL          = var.agent_model
    INBOUND_EMAIL_DOMAIN = var.inbound_email_domain
    SLACK_CLIENT_ID      = var.slack_client_id
  }
}

resource "google_cloud_run_v2_service" "api" {
  name                = "api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.api.email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = var.placeholder_image
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
      dynamic "env" {
        for_each = local.api_env
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = merge(local.api_secrets, local.optional_secrets)
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app[env.key].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.api_reads]
}

resource "google_cloud_run_v2_service" "web" {
  name                = "web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.web.email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = var.placeholder_image
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
      env {
        name  = "API_BASE_URL"
        value = local.api_url
      }
      env {
        name  = "API_AUDIENCE"
        value = local.api_url
      }
      env {
        name  = "SITE_URL"
        value = local.site
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_project_service.enabled]
}

# The lead model (ADR-048): private, called only by the API, holding no data and no secrets.
resource "google_cloud_run_v2_service" "decisioning" {
  name                = "decisioning"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.decisioning.email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.placeholder_image
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
      startup_probe {
        http_get {
          path = "/health"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_project_service.enabled]
}

# Migrations (run by every deploy) and one-off ops commands, from the API image:
#   gcloud run jobs execute ops --region us-west1 --wait \
#     --args=-m,cornerpin.ops,create-tenant,--name,Land Co.,--owner-email,owner@example.com
resource "google_cloud_run_v2_job" "ops" {
  for_each            = { migrate = ["-m", "cornerpin.ops", "migrate"], ops = ["-m", "cornerpin.ops", "check"] }
  name                = each.key
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.ops.email
      max_retries     = 0
      timeout         = "600s"
      containers {
        image   = var.placeholder_image
        command = ["python"]
        args    = each.value
        dynamic "env" {
          for_each = local.api_env
          content {
            name  = env.key
            value = env.value
          }
        }
        dynamic "env" {
          # The same settings as the API, so they pass the same checks at start-up.
          for_each = merge(local.api_secrets, local.optional_secrets, local.job_secrets)
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.app[env.key].secret_id
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.ops_reads]
}
