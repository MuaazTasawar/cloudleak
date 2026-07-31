terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Cost Explorer only lives in us-east-1 - the Lambda itself runs in
# var.aws_region, but we don't need a second provider alias here since
# the collector code hardcodes "ce" client region to us-east-1 directly.
