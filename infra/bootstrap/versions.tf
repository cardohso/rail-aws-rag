terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.70"
    }
  }

  # Local state on purpose: this stack creates the budgets alert first, then the S3
  # bucket that will hold remote state. See the README for the migration step.
}
