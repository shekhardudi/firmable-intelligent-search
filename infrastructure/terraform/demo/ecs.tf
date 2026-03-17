data "aws_caller_identity" "current" {}

locals {
  opensearch_endpoint = "https://${aws_opensearch_domain.main.endpoint}"
  redis_endpoint      = aws_elasticache_cluster.main.cache_nodes[0].address
}

# ---------------------------------------------------------------------------
# ECS Cluster
# ---------------------------------------------------------------------------
resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  # ECS service-linked role is assumed to already exist in the account
}

# ---------------------------------------------------------------------------
# CloudWatch Log Groups
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.name_prefix}/backend"
  retention_in_days = 7
}

# ---------------------------------------------------------------------------
# Backend Task Definition (FastAPI + ADOT sidecar)
# ---------------------------------------------------------------------------
resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name_prefix}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "2048"   # 2 vCPU – SentenceTransformer query encoding + API concurrency
  memory                   = "4096"   # 4 GB  – model (~80 MB) + uvicorn workers + headroom
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = var.backend_image
      essential = true

      portMappings = [{ containerPort = 8000, protocol = "tcp" }]

      environment = [
        { name = "ENVIRONMENT",            value = "demo" },
        { name = "LOG_LEVEL",              value = "INFO" },
        { name = "OPENSEARCH_HOST",        value = replace(local.opensearch_endpoint, "https://", "") },
        { name = "OPENSEARCH_PORT",        value = "443" },
        { name = "OPENSEARCH_USER",        value = var.opensearch_master_user },
        { name = "OPENSEARCH_VERIFY_CERTS", value = "true" },
        { name = "REDIS_URL",             value = "redis://${local.redis_endpoint}:6379" },
        { name = "OTEL_SERVICE_NAME",     value = "firmable-search" },
        { name = "OTLP_ENDPOINT",         value = "http://localhost:4317" },
        { name = "AWS_REGION",            value = var.aws_region },
      ]

      secrets = [
        { name = "OPENSEARCH_PASSWORD", valueFrom = aws_secretsmanager_secret.opensearch_password.arn },
        { name = "OPENAI_API_KEY",      valueFrom = aws_secretsmanager_secret.openai_api_key.arn },
        { name = "TAVILY_API_KEY",      valueFrom = aws_secretsmanager_secret.tavily_api_key.arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    },

    # ADOT sidecar — receives OTLP from app, routes to X-Ray + CloudWatch EMF
    {
      name      = "adot-collector"
      image     = "public.ecr.aws/aws-observability/aws-otel-collector:v0.40.0"
      essential = false

      command = ["--config", "/etc/ecs/ecs-default-config.yaml"]

      environment = [
        { name = "AWS_REGION", value = var.aws_region },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "adot"
        }
      }
    }
  ])
}

# ---------------------------------------------------------------------------
# Data Ingestion Task Definition (one-off ECS run-task)
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/ecs/${local.name_prefix}/ingest"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "ingest" {
  family                   = "${local.name_prefix}-ingest"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "4096"   # 4 vCPU – SentenceTransformer batch encoding is CPU-bound
  memory                   = "8192"   # 8 GB  – headroom for model + pandas DataFrames
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "ingest"
      image     = var.ingest_image
      essential = true

      environment = [
        { name = "OPENSEARCH_HOST",    value = replace(local.opensearch_endpoint, "https://", "") },
        { name = "OPENSEARCH_PORT",    value = "443" },
        { name = "OPENSEARCH_USER",    value = var.opensearch_master_user },
        { name = "INGEST_CSV_S3_URI",  value = "s3://${aws_s3_bucket.data.bucket}/companies_sorted.csv" },
      ]

      secrets = [
        { name = "OPENSEARCH_PASSWORD", valueFrom = aws_secretsmanager_secret.opensearch_password.arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ingest.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ingest"
        }
      }
    }
  ])
}

# ---------------------------------------------------------------------------
# ECS Services
# ---------------------------------------------------------------------------
resource "aws_ecs_service" "backend" {
  name            = "${local.name_prefix}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_backend.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  enable_execute_command = true   # Enables aws ecs execute-command for debug

  # Prevents Terraform from overwriting task_definition after GitHub Actions deploys
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy.ecs_execution_secrets,
  ]
}

# ---------------------------------------------------------------------------
# Auto Scaling — target-track on CPU to handle 30 RPS
# ---------------------------------------------------------------------------
resource "aws_appautoscaling_target" "backend" {
  max_capacity       = 4
  min_capacity       = 2
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "${local.name_prefix}-backend-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 60
    scale_in_cooldown  = 120
    scale_out_cooldown = 60
  }
}
