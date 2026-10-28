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
