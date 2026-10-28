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
