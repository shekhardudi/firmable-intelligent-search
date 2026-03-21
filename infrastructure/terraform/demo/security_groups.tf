# ---------------------------------------------------------------------------
# ALB security group — accepts HTTP from allowed CIDRs
# ---------------------------------------------------------------------------
resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb"
  description = "ALB inbound HTTP"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from allowed CIDRs"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_for_alb
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-alb" }
}

# ---------------------------------------------------------------------------
# ECS Backend security group
# ---------------------------------------------------------------------------
resource "aws_security_group" "ecs_backend" {
  name        = "${local.name_prefix}-ecs-backend"
  description = "ECS backend tasks - only ALB can reach port 8000"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "From ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-ecs-backend" }
}

# ---------------------------------------------------------------------------
# OpenSearch security group
# ---------------------------------------------------------------------------
resource "aws_security_group" "opensearch" {
  name        = "${local.name_prefix}-opensearch"
  description = "OpenSearch - only ECS tasks can reach port 443"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "From ECS backend"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_backend.id]
  }

  ingress {
    description     = "From GPU ingest instances"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.ingest_gpu.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-opensearch" }
}

# ---------------------------------------------------------------------------
# GPU Ingest security group — outbound only (no inbound services)
# ---------------------------------------------------------------------------
resource "aws_security_group" "ingest_gpu" {
  name        = "${local.name_prefix}-ingest-gpu"
  description = "GPU ingest instances - outbound to OpenSearch and VPC endpoints"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-ingest-gpu" }
}

# ---------------------------------------------------------------------------
# ElastiCache (Redis) security group
# ---------------------------------------------------------------------------
resource "aws_security_group" "redis" {
  name        = "${local.name_prefix}-redis"
  description = "Redis - only ECS tasks can reach port 6379"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "From ECS tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_backend.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-redis" }
}

# ---------------------------------------------------------------------------
# VPC Endpoints security group — ECS tasks can reach interface endpoints
# ---------------------------------------------------------------------------
resource "aws_security_group" "vpc_endpoints" {
  name        = "${local.name_prefix}-vpc-endpoints"
  description = "Allow ECS tasks to use VPC Interface Endpoints"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from private subnets"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [for s in aws_subnet.private : s.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-vpc-endpoints" }
}
