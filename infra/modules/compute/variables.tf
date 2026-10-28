variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "lambda_zip_path" {
  description = "Local path of the zip built by scripts/build_lambda.py."
  type        = string
}

variable "data_bucket_name" {
  description = "Bucket that holds the retrieval index. The Lambda zip is stored there too."
  type        = string
}

variable "data_bucket_arn" {
  description = "ARN of the data bucket."
  type        = string
}

variable "index_prefix" {
  description = "Prefix of the index inside the data bucket, for example index/d63c374869fb/."
  type        = string
}

variable "model_id" {
  description = "Bedrock model or EU inference profile that generates answers."
  type        = string
  default     = "eu.amazon.nova-lite-v1:0"
}

variable "guardrail_id" {
  description = "Bedrock guardrail ID."
  type        = string
}

variable "guardrail_arn" {
  description = "Bedrock guardrail ARN."
  type        = string
}

variable "guardrail_version" {
  description = "Numbered guardrail version."
  type        = string
}

variable "quota_table_name" {
  description = "DynamoDB table that counts requests per day."
  type        = string
}

variable "quota_table_arn" {
  description = "ARN of the quota table."
  type        = string
}

variable "daily_limit" {
  description = "Requests per UTC day before the API answers 429."
  type        = number
  default     = 50
}

variable "memory_mb" {
  description = "Lambda memory. 1769 MB is one full vCPU, which the ONNX query encoder uses."
  type        = number
  default     = 1769
}

variable "timeout_seconds" {
  description = "Lambda timeout. API Gateway gives up at 30 seconds."
  type        = number
  default     = 25
}

variable "log_retention_days" {
  description = "Days to keep Lambda logs."
  type        = number
  default     = 7
}

variable "reserved_concurrency" {
  description = "Reserved concurrent executions, or null for none. New accounts have a total limit of 10 and AWS keeps 10 unreserved, so nothing can be reserved until the quota is raised."
  type        = number
  default     = null
}
