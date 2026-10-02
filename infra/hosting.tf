# cornerpin.app through Firebase Hosting to the web service (ADR-032): free at this traffic,
# Google-managed certificate. Hosting forwards only the __session cookie, which is why the
# session cookie has that name.

resource "google_firebase_project" "this" {
  provider   = google-beta
  project    = var.project_id
  depends_on = [google_project_service.enabled]
}

resource "google_firebase_hosting_site" "site" {
  provider   = google-beta
  project    = var.project_id
  site_id    = var.project_id
  depends_on = [google_firebase_project.this]
}

resource "google_firebase_hosting_version" "web" {
  provider = google-beta
  site_id  = google_firebase_hosting_site.site.site_id
  config {
    rewrites {
      glob = "**"
      run {
        service_id = google_cloud_run_v2_service.web.name
        region     = var.region
      }
    }
  }
}

resource "google_firebase_hosting_release" "web" {
  provider     = google-beta
  site_id      = google_firebase_hosting_site.site.site_id
  version_name = google_firebase_hosting_version.web.name
  message      = "Everything goes to the web service on Cloud Run"
}

resource "google_firebase_hosting_custom_domain" "apex" {
  provider              = google-beta
  project               = var.project_id
  site_id               = google_firebase_hosting_site.site.site_id
  custom_domain         = var.domain
  wait_dns_verification = false
}

resource "google_firebase_hosting_custom_domain" "www" {
  provider              = google-beta
  project               = var.project_id
  site_id               = google_firebase_hosting_site.site.site_id
  custom_domain         = "www.${var.domain}"
  redirect_target       = var.domain
  wait_dns_verification = false
  depends_on            = [google_firebase_hosting_custom_domain.apex]
}
