output "bucket_name" {
  description = "Name of the S3 bucket that holds Terraform state."
  value       = aws_s3_bucket.state.id
}
