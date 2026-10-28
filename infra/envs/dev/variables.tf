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
  description = "Address that receives the error alarm. Set it in terraform.tfvars, which is not committed."
  type        = string
}

variable "lambda_zip_path" {
  description = "Zip built by scripts/build_lambda.py, relative to this folder."
  type        = string
  default     = "../../../build/lambda.zip"
}

variable "index_prefix" {
  description = "Prefix of the uploaded index in the data bucket, for example index/d63c374869fb/."
  type        = string
}

variable "model_id" {
  description = "Bedrock model or EU inference profile that generates answers."
  type        = string
  default     = "eu.amazon.nova-lite-v1:0"
}

variable "daily_limit" {
  description = "Requests per UTC day before the API answers 429."
  type        = number
  default     = 50
}

variable "throttle_rate" {
  description = "Steady requests per second the API accepts."
  type        = number
  default     = 1
}

variable "throttle_burst" {
  description = "Burst size above the steady rate."
  type        = number
  default     = 2
}
