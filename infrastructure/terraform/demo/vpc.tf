data "aws_availability_zones" "available" {
  state = "available"
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${local.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.name_prefix}-igw" }
}

# ---------------------------------------------------------------------------
# Public subnets (ALB + NAT Gateway — 2 AZs minimum for ALB requirement)
# ---------------------------------------------------------------------------
resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = { Name = "${local.name_prefix}-public-${count.index}" }
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${local.name_prefix}-nat-eip" }
}

# Single NAT Gateway — only needed for external HTTPS (OpenAI, Tavily).
# AWS-internal traffic uses VPC Endpoints below.
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "${local.name_prefix}-nat" }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.name_prefix}-rtb-public" }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ---------------------------------------------------------------------------
# Private subnets (ECS tasks, OpenSearch, ElastiCache — single AZ for demo)
# ---------------------------------------------------------------------------
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = { Name = "${local.name_prefix}-private-${count.index}" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.name_prefix}-rtb-private" }
}

resource "aws_route" "private_nat" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ---------------------------------------------------------------------------
# VPC Endpoints — eliminate NAT Gateway cost for AWS-internal API calls
# ---------------------------------------------------------------------------

# S3 Gateway endpoint (free)
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  tags              = { Name = "${local.name_prefix}-ep-s3" }
}

# Interface endpoints (charged per hour + data, but cheaper than NAT at scale)
locals {
  interface_endpoints = {
    secretsmanager = "com.amazonaws.${var.aws_region}.secretsmanager"
    ecr_api        = "com.amazonaws.${var.aws_region}.ecr.api"
    ecr_dkr        = "com.amazonaws.${var.aws_region}.ecr.dkr"
    logs           = "com.amazonaws.${var.aws_region}.logs"
    xray           = "com.amazonaws.${var.aws_region}.xray"
    ssm            = "com.amazonaws.${var.aws_region}.ssm"
    ssmmessages    = "com.amazonaws.${var.aws_region}.ssmmessages"
  }
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoints

  vpc_id              = aws_vpc.main.id
  service_name        = each.value
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${local.name_prefix}-ep-${each.key}" }
}
