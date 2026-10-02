# The outbox in the cloud (ADR-010, ADR-029): a Cloud Task per commit that queued events, and
# an hourly Cloud Scheduler drain for retries and anything a dispatch missed, plus housekeeping.
# Hourly, not every minute: each drain wakes the Neon compute, whose free plan has 100
# CU-hours a month (ADR-032).

resource "google_cloud_tasks_queue" "outbox" {
  name     = "outbox"
  location = var.region

  rate_limits {
    max_dispatches_per_second = 5
    max_concurrent_dispatches = 2
  }
  retry_config {
    max_attempts       = 5
    min_backoff        = "5s"
    max_backoff        = "300s"
    max_retry_duration = "3600s"
  }

  depends_on = [google_project_service.enabled]
}

resource "google_cloud_scheduler_job" "internal" {
  for_each = {
    drain-outbox = { schedule = "7 * * * *", path = "/internal/outbox/drain" }
    housekeeping = { schedule = "17 9 * * *", path = "/internal/housekeeping" }
  }
  name      = each.key
  region    = var.region
  schedule  = each.value.schedule
  time_zone = "America/Boise"

  retry_config {
    retry_count = 1
  }
  http_target {
    http_method = "POST"
    uri         = "${local.api_url}${each.value.path}"
    oidc_token {
      service_account_email = google_service_account.tasks.email
      audience              = local.api_url
    }
  }

  depends_on = [google_project_service.enabled]
}
