terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment and configure for remote state (recommended before sharing):
  # backend "s3" {
  #   bucket = "firmable-tf-state"
  #   key    = "demo/terraform.tfstate"
  #   region = "ap-southeast-2"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "firmable-demo"
      Environment = "demo"
      ManagedBy   = "terraform"
    }
  }
}

locals {
  name_prefix = "firmable-demo"
}

# ---------------------------------------------------------------------------
# AWS Resource Group -- groups all demo resources in the Console
# ---------------------------------------------------------------------------
resource "aws_resourcegroups_group" "demo" {
  name = local.name_prefix

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [{
        Key    = "Project"
        Values = ["firmable-demo"]
      }]
    })
  }

  tags = { Name = "${local.name_prefix}-resource-group" }
}
