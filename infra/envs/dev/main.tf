provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.name_prefix
      ManagedBy = "terraform"
    }
  }
}

module "storage" {
  source = "../../modules/storage"

  name_prefix   = var.name_prefix
  force_destroy = true # the index is rebuilt from the repo, so a destroy must not get stuck on it
  index_dir     = var.index_dir
}

module "quota" {
  source = "../../modules/quota"

  name_prefix = var.name_prefix
}

module "guardrail" {
  source = "../../modules/bedrock_guardrail"

  name_prefix = var.name_prefix
}

module "compute" {
  source = "../../modules/compute"

  name_prefix       = var.name_prefix
  lambda_zip_path   = var.lambda_zip_path
  data_bucket_name  = module.storage.bucket_name
  data_bucket_arn   = module.storage.bucket_arn
  index_prefix      = module.storage.index_prefix
  model_id          = var.model_id
  guardrail_id      = module.guardrail.guardrail_id
  guardrail_arn     = module.guardrail.guardrail_arn
  guardrail_version = module.guardrail.guardrail_version
  quota_table_name  = module.quota.table_name
  quota_table_arn   = module.quota.table_arn
  daily_limit       = var.daily_limit
}

module "api" {
  source = "../../modules/api"

  name_prefix    = var.name_prefix
  function_name  = module.compute.function_name
  invoke_arn     = module.compute.invoke_arn
  throttle_rate  = var.throttle_rate
  throttle_burst = var.throttle_burst
}

module "monitoring" {
  source = "../../modules/monitoring"

  name_prefix    = var.name_prefix
  alert_email    = var.alert_email
  api_id         = module.api.api_id
  function_name  = module.compute.function_name
  log_group_name = module.compute.log_group_name
  model_id       = var.model_id
}
