output "alb_dns_name" {
  description = "ALB DNS name — used as the CloudFront ALB origin."
  value       = aws_lb.main.dns_name
}

output "cloudfront_url" {
  description = "CloudFront distribution domain — use this as the demo URL."
  value       = aws_cloudfront_distribution.main.domain_name
}

output "frontend_bucket_name" {
  description = "S3 bucket name to upload the built frontend SPA."
  value       = aws_s3_bucket.frontend.bucket
}

output "data_bucket_name" {
  description = "S3 bucket name for ingestion data (CSV files)."
  value       = aws_s3_bucket.data.bucket
}

output "opensearch_endpoint" {
  description = "OpenSearch domain endpoint (HTTPS)."
  value       = "https://${aws_opensearch_domain.main.endpoint}"
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint."
  value       = "${aws_elasticache_cluster.main.cache_nodes[0].address}:6379"
}

output "ecs_cluster_name" {
  description = "ECS cluster name (used by deploy scripts)."
  value       = aws_ecs_cluster.main.name
}

output "ecs_backend_sg_id" {
  description = "Backend ECS security group ID (used by one-off ingest task)."
  value       = aws_security_group.ecs_backend.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs (used by one-off ingest task)."
  value       = aws_subnet.private[*].id
}

output "backend_task_definition" {
  description = "Latest backend task definition ARN."
  value       = aws_ecs_task_definition.backend.arn
}

output "ingest_gpu_asg_name" {
  description = "Auto Scaling Group name for GPU ingest instances."
  value       = aws_autoscaling_group.ingest_gpu.name
}
