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
# Data Ingestion — GPU EC2 (g4dn.xlarge) running code directly from S3
# ---------------------------------------------------------------------------
# No Docker image needed. The instance boots, downloads the data-pipeline
# code from S3, pip-installs dependencies, runs the pipeline, then shuts down.
# ASG starts at 0; deploy-all.sh sets desired=1 to trigger ingestion.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/ecs/${local.name_prefix}/ingest"
  retention_in_days = 7
}

# ARM64 AMI (Amazon Linux 2023 for Graviton)
data "aws_ssm_parameter" "al2023_arm" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_launch_template" "ingest_gpu" {
  name          = "${local.name_prefix}-ingest-gpu"
  image_id      = data.aws_ssm_parameter.al2023_arm.value
  instance_type = "c7g.4xlarge"   # Graviton3, 16 vCPU, 32 GB RAM, BF16

  iam_instance_profile { arn = aws_iam_instance_profile.ingest_gpu.arn }

  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.ingest_gpu.id]
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 50   # OS + pip packages + model cache
      volume_type           = "gp3"
      delete_on_termination = true
    }
  }

  # Download code from S3, install deps, run ingestion, then shutdown
  user_data = base64encode(<<-USERDATA
#!/bin/bash
set -euxo pipefail
exec > /var/log/ingest.log 2>&1

REGION="${var.aws_region}"
DATA_BUCKET="${aws_s3_bucket.data.bucket}"
OPENSEARCH_HOST="${replace(local.opensearch_endpoint, "https://", "")}"
OPENSEARCH_PORT="443"
OPENSEARCH_USER="${var.opensearch_master_user}"
SECRET_ARN="${aws_secretsmanager_secret.opensearch_password.arn}"
ASG_NAME="${local.name_prefix}-ingest-gpu"

# Fetch OpenSearch password from Secrets Manager
OPENSEARCH_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id "$SECRET_ARN" --region "$REGION" \
  --query SecretString --output text)

# Install Python 3.11 + pip (AL2023 ships Python 3.9)
dnf install -y python3.11 python3.11-pip python3.11-devel gcc gcc-c++

# Download pipeline code from S3
mkdir -p /opt/ingest && cd /opt/ingest
aws s3 cp "s3://$DATA_BUCKET/data-pipeline.tar.gz" - | tar xzf -

# Install Python dependencies (CPU-only torch for ARM/Graviton)
python3.11 -m pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
python3.11 -m pip install --no-cache-dir -r requirements.txt

# Run the ingestion pipeline
export OPENSEARCH_HOST OPENSEARCH_PORT OPENSEARCH_USER OPENSEARCH_PASSWORD
python3.11 data_ingestion_pipeline.py \
  --csv "s3://$DATA_BUCKET/companies_sorted.csv" \
  --host "$OPENSEARCH_HOST" \
  --port "$OPENSEARCH_PORT" \
  --reset

# Scale ASG back to 0 — instance will be terminated
aws autoscaling set-desired-capacity \
  --auto-scaling-group-name "$ASG_NAME" \
  --desired-capacity 0 \
  --region "$REGION"

shutdown -h now
USERDATA
  )

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${local.name_prefix}-ingest-gpu" }
  }
}

resource "aws_autoscaling_group" "ingest_gpu" {
  name                = "${local.name_prefix}-ingest-gpu"
  desired_capacity    = 0   # Starts at 0 — deploy-all.sh sets to 1
  min_size            = 0
  max_size            = 1
  vpc_zone_identifier = aws_subnet.private[*].id

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 1    # Fallback to on-demand if no spot
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "capacity-optimized"
      spot_max_price                           = "0.80"
    }

    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.ingest_gpu.id
        version            = "$Latest"
      }

      # Graviton3 instances — Standard quota (64 vCPU available)
      override {
        instance_type = "c7g.4xlarge"    # 16 vCPU, 32 GB — best perf/cost
      }
      override {
        instance_type = "c7g.2xlarge"    # 8 vCPU, 16 GB — smaller fallback
      }
      override {
        instance_type = "c6g.4xlarge"    # 16 vCPU, 32 GB — Graviton2 fallback
      }
      override {
        instance_type = "m7g.4xlarge"    # 16 vCPU, 64 GB — memory-rich fallback
      }
    }
  }

  lifecycle {
    ignore_changes = [desired_capacity]
  }
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
