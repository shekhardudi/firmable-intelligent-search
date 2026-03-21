variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-southeast-2"
}

variable "backend_image" {
  description = "Full ECR image URI for the FastAPI backend (e.g. 123456789.dkr.ecr.ap-southeast-2.amazonaws.com/firmable-backend:latest)."
  type        = string
}

variable "opensearch_password" {
  description = "Master password for the OpenSearch domain. Min 8 chars, upper+lower+digit+symbol."
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key stored in Secrets Manager."
  type        = string
  sensitive   = true
}

variable "tavily_api_key" {
  description = "Tavily search API key stored in Secrets Manager."
  type        = string
  sensitive   = true
}

variable "opensearch_master_user" {
  description = "Master username for the OpenSearch domain."
  type        = string
  default     = "firmable"
}

variable "vpc_cidr" {
  description = "CIDR block for the demo VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "allowed_cidr_for_alb" {
  description = "CIDR allowed to reach the ALB on port 80. Set to your office IP for added security."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
