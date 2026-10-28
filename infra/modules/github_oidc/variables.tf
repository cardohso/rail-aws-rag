variable "name_prefix" {
  description = "Prefix of every resource the deploy role may manage."
  type        = string
}

variable "github_repository" {
  description = "owner/name of the repository whose workflows may assume the roles."
  type        = string
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
