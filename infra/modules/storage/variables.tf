variable "name_prefix" {
  description = "Prefix for the bucket name. The account ID is appended to keep the name unique."
  type        = string
}

variable "force_destroy" {
  description = "Let terraform destroy delete the bucket even if it holds objects. The index is rebuilt from the repo, so this is safe here."
  type        = bool
  default     = false
}
