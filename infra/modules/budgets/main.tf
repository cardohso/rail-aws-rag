resource "aws_budgets_budget" "monthly" {
  name         = "${var.name_prefix}-monthly-cost"
  budget_type  = "COST"
  limit_amount = tostring(var.limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Gross usage cost. With credits netted out, the Free plan's credits would keep
  # the budgeted amount at 0 USD and no alert would ever fire.
  cost_types {
    include_credit = false
    include_refund = false
  }

  dynamic "notification" {
    for_each = toset(var.actual_thresholds_usd)

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "ABSOLUTE_VALUE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alert_email]
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
