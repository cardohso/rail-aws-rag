variable "name_prefix" {
  description = "Prefix of every resource the deploy role may manage."
  type        = string
}

variable "oidc_subject_prefix" {
  description = "Start of the OIDC `sub` claim for the repository. Newer repositories use immutable subjects that carry the owner and repository IDs, e.g. repo:owner@123/name@456; read it with `gh api repos/OWNER/REPO/actions/oidc/customization/sub` (sub_claim_prefix)."
  type        = string

  validation {
    condition     = startswith(var.oidc_subject_prefix, "repo:")
    error_message = "oidc_subject_prefix starts with repo:"
  }
}

variable "deploy_environment" {
  description = "GitHub environment that gates the deploy role (it has a required reviewer)."
  type        = string
  default     = "production"
}

variable "state_bucket_name" {
  description = "Bucket that holds Terraform state."
  type        = string
}

variable "state_key_prefix" {
  description = "Folder of the state the roles may lock and write: CI manages the dev stack only."
  type        = string
  default     = "dev/"
}
