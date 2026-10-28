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
}
