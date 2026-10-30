terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.70"
    }
  }

  # Remote state in the bucket created by infra/bootstrap. Bucket and key come from backend.hcl
  # (not committed):  terraform init -backend-config=backend.hcl
  backend "s3" {}
}
