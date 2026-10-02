output "api_url" {
  description = "The private API (only the web app and Cloud Tasks may call it)."
  value       = google_cloud_run_v2_service.api.uri
}

output "web_url" {
  value = google_cloud_run_v2_service.web.uri
}

output "hosting_url" {
  description = "Works before DNS is set up."
  value       = "https://${google_firebase_hosting_site.site.site_id}.web.app"
}

output "dns_records" {
  description = "Add these at the domain's registrar."
  value = {
    apex = google_firebase_hosting_custom_domain.apex.required_dns_updates
    www  = google_firebase_hosting_custom_domain.www.required_dns_updates
  }
}

output "registry" {
  value = local.registry
}

output "github_variables" {
  description = "Repository variables the deploy workflow reads (gh variable set NAME --body VALUE)."
  value = {
    GCP_PROJECT_ID   = var.project_id
    GCP_REGION       = var.region
    GCP_WIF_PROVIDER = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOYER     = google_service_account.deployer.email
    GCP_REGISTRY     = local.registry
  }
}
