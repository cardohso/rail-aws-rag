output "bucket_name" {
  description = "Name of the bucket that holds the retrieval index."
  value       = aws_s3_bucket.data.id
}

output "bucket_arn" {
  description = "ARN of the bucket that holds the retrieval index."
  value       = aws_s3_bucket.data.arn
}
