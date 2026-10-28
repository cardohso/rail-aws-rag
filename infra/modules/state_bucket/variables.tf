variable "name_prefix" {
  description = "Prefix for the bucket name. The account ID is appended to keep the name unique."
  type        = string
}

variable "noncurrent_version_days" {
  description = "Days to keep old state versions before they expire."
  type        = number
  default     = 30
}
