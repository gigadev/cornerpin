data "google_project" "this" {
  project_id = var.project_id
}

locals {
  services = [
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtasks.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ]

  # Cloud Run's deterministic URL. The API needs its own address (as the audience of the
  # OIDC tokens Cloud Tasks sends it) before Terraform could read it back from the service.
  api_url = "https://api-${data.google_project.this.number}.${var.region}.run.app"
  site    = "https://${var.domain}"
}

resource "google_project_service" "enabled" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}
