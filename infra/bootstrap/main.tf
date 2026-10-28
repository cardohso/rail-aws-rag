provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.name_prefix
      ManagedBy = "terraform"
    }
  }
}

# First resource of the project, before anything else can cost money.
module "budgets" {
  source = "../modules/budgets"

  name_prefix = var.name_prefix
  alert_email = var.alert_email
}

# Holds the remote state of every stack, including this one after the migration.
module "state_bucket" {
  source = "../modules/state_bucket"

  name_prefix = var.name_prefix
}

# GitHub Actions sign in with short-lived OIDC tokens: no AWS keys are stored in GitHub.
module "github_oidc" {
  source = "../modules/github_oidc"

  name_prefix       = var.name_prefix
  github_repository = var.github_repository
  state_bucket_name = module.state_bucket.bucket_name
}
