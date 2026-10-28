variable "aws_region" {
  description = "Region for all resources."
  type        = string
  default     = "eu-west-1"
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "rail-aws-rag"
}

variable "alert_email" {
  description = "Address that receives the budget alerts. Set it in terraform.tfvars, which is not committed."
  type        = string
  sensitive   = true # plans in public CI logs must not print it

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "oidc_subject_prefix" {
  description = "sub_claim_prefix from `gh api repos/OWNER/REPO/actions/oidc/customization/sub`."
  type        = string
  default     = "repo:cardohso@119709544/rail-aws-rag@1437518588"
}
