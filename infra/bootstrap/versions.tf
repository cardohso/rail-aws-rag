terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.70"
    }
  }

  # This stack created the budgets alert and the state bucket with local state, then moved
  # its own state into that bucket. Bucket and key come from backend.hcl (not committed):
  #   terraform init -backend-config=backend.hcl
  backend "s3" {}
}
