variable "name_prefix" {
  description = "Prefix for the budget name."
  type        = string
}

variable "alert_email" {
  description = "Address that receives the budget alerts."
  type        = string
  sensitive   = true # plans in public CI logs must not print it
}

variable "limit_usd" {
  description = "Monthly cost budget in USD. The forecast alert fires at 100% of it."
  type        = number
  default     = 5
}

variable "actual_thresholds_usd" {
  description = "Alert when actual month-to-date cost goes above each of these USD amounts."
  type        = list(number)
  default     = [1, 5]
}
