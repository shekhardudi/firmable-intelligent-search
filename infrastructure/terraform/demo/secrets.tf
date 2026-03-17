resource "aws_secretsmanager_secret" "openai_api_key" {
  name                    = "${local.name_prefix}/openai-api-key"
  recovery_window_in_days = 0   # Immediate deletion — demo environment
}

resource "aws_secretsmanager_secret_version" "openai_api_key" {
  secret_id     = aws_secretsmanager_secret.openai_api_key.id
  secret_string = var.openai_api_key
}

resource "aws_secretsmanager_secret" "tavily_api_key" {
  name                    = "${local.name_prefix}/tavily-api-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "tavily_api_key" {
  secret_id     = aws_secretsmanager_secret.tavily_api_key.id
  secret_string = var.tavily_api_key
}

resource "aws_secretsmanager_secret" "opensearch_password" {
  name                    = "${local.name_prefix}/opensearch-password"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "opensearch_password" {
  secret_id     = aws_secretsmanager_secret.opensearch_password.id
  secret_string = var.opensearch_password
}
