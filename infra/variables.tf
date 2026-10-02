variable "project_id" {
  description = "Google Cloud project that holds everything."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account the project is linked to (for the budget alert)."
  type        = string
}

variable "region" {
  description = "Cloud Run, Cloud Tasks and storage region (ADR-032)."
  type        = string
  default     = "us-west1"
}

variable "domain" {
  description = "The public site, served through Firebase Hosting."
  type        = string
  default     = "cornerpin.app"
}

variable "github_repository" {
  description = "owner/name of the repo whose Actions may deploy."
  type        = string
  default     = "gigadev/cornerpin"
}

variable "budget_usd" {
  description = "Monthly budget; alerts at 50, 90 and 100 percent."
  type        = number
  default     = 5
}

variable "email_from" {
  description = "Sender for sign-in links and alerts; its domain must be verified in Resend."
  type        = string
  default     = "Cornerpin <hello@cornerpin.app>"
}

variable "turnstile_site_key" {
  description = "Cloudflare Turnstile site key for the domain (public)."
  type        = string
}

variable "vapid_public_key" {
  description = "Web push public key; empty keeps push off (ADR-029)."
  type        = string
  default     = ""
}

variable "placeholder_image" {
  description = "Image Cloud Run starts with before the first deploy replaces it."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
