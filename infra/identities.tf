# One service account per job, each with only what it needs (ADR-032).

resource "google_service_account" "api" {
  account_id   = "cornerpin-api"
  display_name = "Cornerpin API (Cloud Run)"
}

resource "google_service_account" "web" {
  account_id   = "cornerpin-web"
  display_name = "Cornerpin web app (Cloud Run)"
}

resource "google_service_account" "ops" {
  account_id   = "cornerpin-ops"
  display_name = "Migrations and ops commands (Cloud Run jobs)"
}

resource "google_service_account" "tasks" {
  account_id   = "cornerpin-tasks"
  display_name = "Cloud Tasks and Scheduler calling the API"
}

resource "google_service_account" "deployer" {
  account_id   = "cornerpin-deployer"
  display_name = "GitHub Actions deploys"
}

# The API is private: only the web app and Cloud Tasks/Scheduler may call it.
resource "google_cloud_run_v2_service_iam_member" "api_invokers" {
  for_each = {
    web   = google_service_account.web.email
    tasks = google_service_account.tasks.email
  }
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${each.value}"
}

# The web app is public; Firebase Hosting forwards to it.
resource "google_cloud_run_v2_service_iam_member" "web_public" {
  name     = google_cloud_run_v2_service.web.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# The API queues Cloud Tasks that carry the tasks account's OIDC token.
resource "google_cloud_tasks_queue_iam_member" "api_enqueue" {
  name     = google_cloud_tasks_queue.outbox.name
  location = var.region
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.api.email}"
}

resource "google_service_account_iam_member" "api_acts_as_tasks" {
  service_account_id = google_service_account.tasks.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.api.email}"
}

# Deploys: push images, update services and jobs that run as the api and web accounts.
resource "google_project_iam_member" "deployer" {
  for_each = toset(["roles/run.developer", "roles/artifactregistry.writer"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_acts_as" {
  for_each = {
    api = google_service_account.api.name
    web = google_service_account.web.name
    ops = google_service_account.ops.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# Keyless sign-in for GitHub Actions in this repository only.
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "cornerpin"
  display_name                       = "gigadev/cornerpin"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_deploys" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}
