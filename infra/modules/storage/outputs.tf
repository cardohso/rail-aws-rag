output "bucket_name" {
  description = "Name of the bucket that holds the retrieval index."
  value       = aws_s3_bucket.data.id
}

output "bucket_arn" {
  description = "ARN of the bucket that holds the retrieval index."
  value       = aws_s3_bucket.data.arn
}

output "index_prefix" {
  description = "Prefix of the uploaded index, for example index/d63c374869fb/."
  value       = local.index_prefix
  depends_on  = [aws_s3_object.index]
}
