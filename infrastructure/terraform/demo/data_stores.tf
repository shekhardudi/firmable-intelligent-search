# ---------------------------------------------------------------------------
# OpenSearch Service
# ---------------------------------------------------------------------------
resource "aws_opensearch_domain" "main" {
  domain_name    = "${local.name_prefix}-search"
  engine_version = "OpenSearch_2.17"

  cluster_config {
    instance_type  = "r6g.xlarge.search"   # 32 GB – fp16-quantized 7M × 384-dim HNSW needs ~7 GB native, 16 GB native headroom
    instance_count = 1
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = 100   # 7M docs w/ fp16 vectors + HNSW on disk + merge headroom
  }

  vpc_options {
    subnet_ids         = [aws_subnet.private[0].id]
    security_group_ids = [aws_security_group.opensearch.id]
  }

  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = true

    master_user_options {
      master_user_name     = var.opensearch_master_user
      master_user_password = var.opensearch_password
    }
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "*" }
      Action    = "es:*"
      Resource  = "arn:aws:es:${var.aws_region}:${data.aws_caller_identity.current.account_id}:domain/${local.name_prefix}-search/*"
    }]
  })

  tags = { Name = "${local.name_prefix}-opensearch" }
}

# ---------------------------------------------------------------------------
# ElastiCache (Redis)
# ---------------------------------------------------------------------------
resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-redis-subnet"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "${local.name_prefix}-redis"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.1"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]

  tags = { Name = "${local.name_prefix}-redis" }
}

# ---------------------------------------------------------------------------
# S3 Bucket — ingestion data (CSV files uploaded before running the pipeline)
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "data" {
  bucket = "${local.name_prefix}-data-${data.aws_caller_identity.current.account_id}"
  tags   = { Name = "${local.name_prefix}-data" }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}
