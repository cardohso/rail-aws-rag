output "data_bucket_name" {
  description = "Bucket that holds the retrieval index. Upload build/index here."
  value       = module.storage.bucket_name
}
