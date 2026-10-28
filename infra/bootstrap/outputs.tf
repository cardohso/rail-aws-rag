output "state_bucket_name" {
  description = "Bucket for remote Terraform state. Put it in backend.hcl."
  value       = module.state_bucket.bucket_name
}
