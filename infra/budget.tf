# Emails the billing account's admins at 50, 90 and 100 percent of the monthly budget
# (ADR-016). Scott approved $5 on 2026-10-01.
resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account_id
  display_name    = "Cornerpin monthly"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_usd)
    }
  }
  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  depends_on = [google_project_service.enabled]
}
