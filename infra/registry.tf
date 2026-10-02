resource "google_artifact_registry_repository" "images" {
  repository_id = "cornerpin"
  location      = var.region
  format        = "DOCKER"
  description   = "API and web images, pushed by the deploy workflow."

  # Stay inside the free 0.5 GB: keep the ten newest images of each and delete the rest.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
  cleanup_policies {
    id     = "delete-older"
    action = "DELETE"
    condition {
      older_than = "604800s"
    }
  }

  depends_on = [google_project_service.enabled]
}

locals {
  registry = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}
