variable "name_prefix" {
  description = "Prefix for the table name."
  type        = string
}

# One item per UTC day. The Lambda adds 1 to it while it is below the daily limit; DynamoDB's
# TTL deletes old days, so the table never grows.
resource "aws_dynamodb_table" "quota" {
  # checkov:skip=CKV_AWS_28:Point-in-time recovery adds cost for counters that reset daily.
  # checkov:skip=CKV_AWS_119:The AWS-owned key is free; a customer-managed KMS key is about 1 USD a month.
  name         = "${var.name_prefix}-daily-quota"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "day"

  attribute {
    name = "day"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

output "table_name" {
  description = "Name of the daily quota table."
  value       = aws_dynamodb_table.quota.name
}

output "table_arn" {
  description = "ARN of the daily quota table."
  value       = aws_dynamodb_table.quota.arn
}
