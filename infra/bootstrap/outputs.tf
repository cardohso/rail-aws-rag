output "state_bucket_name" {
  description = "Bucket for remote Terraform state. Put it in backend.hcl."
  value       = module.state_bucket.bucket_name
}

output "ci_plan_role_arn" {
  description = "Store as the AWS_PLAN_ROLE_ARN secret in GitHub."
  value       = module.github_oidc.plan_role_arn
}

output "ci_deploy_role_arn" {
  description = "Store as the AWS_DEPLOY_ROLE_ARN secret in GitHub."
  value       = module.github_oidc.deploy_role_arn
}
