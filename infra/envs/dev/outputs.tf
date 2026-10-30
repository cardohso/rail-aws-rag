output "data_bucket_name" {
  description = "Bucket that holds the retrieval index. Upload build/index here."
  value       = module.storage.bucket_name
}

output "api_url" {
  description = "Base URL of the API: POST /ask and GET /health."
  value       = module.api.invoke_url
}

output "dashboard_name" {
  description = "CloudWatch dashboard."
  value       = module.monitoring.dashboard_name
}

output "guardrail_id" {
  description = "Bedrock guardrail ID."
  value       = module.guardrail.guardrail_id
}
