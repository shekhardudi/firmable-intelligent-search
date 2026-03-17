data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ---------------------------------------------------------------------------
# ECS Execution Role — used by the ECS agent to pull images and write logs
# ---------------------------------------------------------------------------
resource "aws_iam_role" "ecs_execution" {
  name               = "${local.name_prefix}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow execution role to read secrets (for injecting into container env)
data "aws_iam_policy_document" "ecs_execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.openai_api_key.arn,
      aws_secretsmanager_secret.tavily_api_key.arn,
      aws_secretsmanager_secret.opensearch_password.arn,
    ]
  }
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name   = "read-secrets"
  role   = aws_iam_role.ecs_execution.id
  policy = data.aws_iam_policy_document.ecs_execution_secrets.json
}

# ---------------------------------------------------------------------------
# ECS Task Role — used by the application container at runtime
# ---------------------------------------------------------------------------
resource "aws_iam_role" "ecs_task" {
  name               = "${local.name_prefix}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

data "aws_iam_policy_document" "ecs_task_permissions" {
  # Secrets Manager — read secrets at runtime (fallback if not injected via env)
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.openai_api_key.arn,
      aws_secretsmanager_secret.tavily_api_key.arn,
      aws_secretsmanager_secret.opensearch_password.arn,
    ]
  }

  # X-Ray — ADOT sidecar sends traces
  statement {
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets",
    ]
    resources = ["*"]
  }

  # CloudWatch Metrics (EMF) — ADOT sidecar writes via CloudWatch Logs
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:*:*:log-group:/ecs/firmable*",
      "arn:aws:logs:*:*:log-group:/aws/ecs/application/metrics*",
    ]
  }

  # ECS Exec (optional — enables `aws ecs execute-command` for debugging)
  statement {
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }

  # S3 — ingest task downloads the CSV from the data bucket
  statement {
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.data.arn,
      "${aws_s3_bucket.data.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task_permissions" {
  name   = "task-permissions"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_permissions.json
}

