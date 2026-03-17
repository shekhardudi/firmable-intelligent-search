# Demo Architecture — AWS Single-Region

Single-AZ deployment sized for 7 M company records with 384-dim fp16 vector
embeddings, ~30 RPS sustained. Optimised for **cost-efficiency** while keeping
query latency low.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AWS Demo Architecture                              │
│                                                                             │
│   Internet                                                                  │
│      │                                                                      │
│      ▼                                                                      │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  Amazon CloudFront  (*.cloudfront.net — no custom domain needed)     │  │
│   │                                                                      │  │
│   │   /*       → S3 Bucket  (frontend SPA static assets)                 │  │
│   │   /api/*   → ALB        (backend FastAPI, HTTP)                      │  │
│   └───────────────┬──────────────────────────┬───────────────────────────┘  │
│                   │                          │                              │
│   ┌───────────────▼──────────┐  ┌────────────▼───────────────────────── ┐   │
│   │  S3 Bucket (frontend)    │  │  Application Load Balancer            │   │
│   │  Static SPA bundle       │  │  Listener: HTTP :80                   │   │
│   │  CloudFront OAC only     │  │  → backend ECS target group           │   │
│   └──────────────────────────┘  └────────────┬───────────────────────── ┘   │
│                                              │                              │
│   ┌──────────────────────────────────────────▼───────────────────────── ┐   │
│   │  VPC  10.0.0.0/16                                                   │   │
│   │                                                                     │   │
│   │  ┌────────────────────────────────────────────────────────────┐     │   │
│   │  │  ECS Cluster (Fargate)  — single AZ                        │     │   │
│   │  │                                                            │     │   │
│   │  │  ┌──────────────────────────────────────────────────┐      │     │   │
│   │  │  │  Backend Service  (FastAPI + ADOT sidecar)       │      │     │   │
│   │  │  │  Tasks: 2–4 (CPU target-tracking auto-scaling)   │      │     │   │
│   │  │  │  CPU: 2 vCPU   Memory: 4 GB  per task            │      │     │   │
│   │  │  │  Embedding model loaded eagerly at startup       │      │     │   │
│   │  │  └──────────────────────────────────────────────────┘      │     │   │
│   │  │                                                            │     │   │
│   │  │  ┌──────────────────────────────────────────────────┐      │     │   │
│   │  │  │  Ingest Task  (one-off ECS run-task)             │      │     │   │
│   │  │  │  CPU: 4 vCPU   Memory: 8 GB                      │      │     │   │
│   │  │  │  SentenceTransformer batch encoding (7 M records)│      │     │   │
│   │  │  └──────────────────────────────────────────────────┘      │     │   │
│   │  │                                                            │     │   │
│   │  └────────────────────────────────────────────────────────────┘     │   │
│   │                                                                     │   │
│   │  ┌──────────────────────┐   ┌────────────────────────────────┐      │   │
│   │  │  Amazon OpenSearch   │   │  ElastiCache (Redis OSS)       │      │   │
│   │  │  r6g.large.search    │   │  cache.t4g.micro               │      │   │
│   │  │  1 node, 100 GB gp3  │   │  Single node (no replica)      │      │   │
│   │  │  kNN + fp16 SQ       │   └────────────────────────────────┘      │   │
│   │  │  7M × 384-dim vecs   │                                           │   │
│   │  └──────────────────────┘                                           │   │
│   │                                                                     │   │
│   │  ┌──────────────────────────────────────────────────────────┐       │   │
│   │  │  AWS Secrets Manager                                     │       │   │
│   │  │  OPENAI_API_KEY · TAVILY_API_KEY · OPENSEARCH_PASSWORD   │       │   │
│   │  └──────────────────────────────────────────────────────────┘       │   │
│   │                                                                     │   │
│   │  ┌──────────────────────────────────────────────────────────┐       │   │
│   │  │  VPC Endpoints (avoid NAT cost on AWS-internal calls)    │       │   │
│   │  │  Gateway : S3                                            │       │   │
│   │  │  Interface: SecretsManager · ECR API · ECR DKR           │       │   │
│   │  │             CloudWatch Logs · X-Ray                      │       │   │
│   │  └──────────────────────────────────────────────────────────┘       │   │
│   │                                                                     │   │
│   └──────────────────────────────────────────────────────────────────── ┘   │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────── ┐  │
│   │  Observability (same zero-code-change pattern as production)         │  │
│   │                                                                      │  │
│   │  App → OTLP/gRPC → ADOT sidecar (localhost:4317)                     │  │
│   │    ├── traces  → AWS X-Ray                                           │  │
│   │    ├── metrics → CloudWatch Metrics (EMF)                            │  │
│   │    └── logs    → CloudWatch Logs (awslogs driver)                    │  │
│   └───────────────────────────────────────────────────────────────────── ┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```
## Key Differences vs Production

| Aspect                | Demo                          | Production                        |
|-----------------------|-------------------------------|-----------------------------------|
| Availability Zones    | Single AZ                     | Multi-AZ (2+)                     |
| Frontend hosting      | CloudFront + S3               | CloudFront + S3 (multi-region)    |
| OpenSearch nodes      | 1 × r6g.large (fp16 SQ)       | 3 × r6g.xlarge (fp16 SQ)          |
| ElastiCache nodes     | 1 × t4g.micro                 | 2 shards + 1 replica each         |
| ECS tasks             | 2–4 backend (auto-scaled)     | 4–20 backend                      |
| Auto-scaling          | CPU target-tracking at 60%    | CPU + p95 latency target tracking |
| TLS                   | CloudFront default cert       | ACM cert + Route 53               |
| Backup / snapshots    | None                          | Daily automated snapshots         |
| Container Insights    | Enabled (same as prod)        | Enabled                           |

## Quick-Start Steps

```bash
# 1. Build and push Docker images
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=ap-southeast-2
REGISTRY=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com

aws ecr create-repository --repository-name firmable-backend  2>/dev/null || true
aws ecr create-repository --repository-name firmable-ingest   2>/dev/null || true

aws ecr get-login-password --region $REGION \
  | docker login --username AWS --password-stdin $REGISTRY

# Backend
docker build -t firmable-backend ./backend
docker tag firmable-backend:latest ${REGISTRY}/firmable-backend:latest
docker push ${REGISTRY}/firmable-backend:latest

# Data-pipeline (ingest)
docker build -t firmable-ingest ./data-pipeline
docker tag firmable-ingest:latest ${REGISTRY}/firmable-ingest:latest
docker push ${REGISTRY}/firmable-ingest:latest

# 2. Deploy infrastructure
cd infrastructure/terraform/demo
terraform init
terraform apply -auto-approve \
  -var="backend_image=${REGISTRY}/firmable-backend:latest" \
  -var="ingest_image=${REGISTRY}/firmable-ingest:latest" \
  -var='opensearch_password=MySecurePassword123!' \
  -var="openai_api_key=$OPENAI_API_KEY" \
  -var="tavily_api_key=$TAVILY_API_KEY"

# 3. Upload CSV data to S3 (ingest task reads from here)
DATA_BUCKET=$(terraform output -raw data_bucket_name)
aws s3 cp ../../../data-pipeline/companies_sorted.csv s3://$DATA_BUCKET/companies_sorted.csv

# 4. Build and deploy the frontend SPA
BUCKET=$(terraform output -raw frontend_bucket_name)
CF_URL=$(terraform output -raw cloudfront_url)

cd ../../../frontend
npm ci
VITE_API_BASE_URL="https://$CF_URL" npm run build
aws s3 sync dist/ s3://$BUCKET/ --delete

# 5. Run data ingestion (one-off ECS task using the ingest image)
cd ../infrastructure/terraform/demo
CLUSTER=$(terraform output -raw ecs_cluster_name)
SUBNET=$(terraform output -json private_subnet_ids | jq -r '.[0]')
SG=$(terraform output -raw ecs_backend_sg_id)

aws ecs run-task \
  --cluster $CLUSTER \
  --task-definition $(terraform output -raw ingest_task_definition) \
  --launch-type FARGATE \
  --region $REGION \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}"

# 6. Warm up (run before the demo)
for q in "fintech startups sydney" "saas companies 50 to 200 employees" "mining companies australia"; do
  curl -s "https://$CF_URL/api/search?q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$q'))")" > /dev/null
done
echo "Demo ready → https://$CF_URL"
```

## Tear-Down (after demo)

```bash
# Stop compute only — data persists for next demo session
aws ecs update-service --cluster $CLUSTER --service firmable-demo-backend --desired-count 0

# Full destroy (deletes all data including S3 buckets)
aws s3 rm s3://$(terraform output -raw frontend_bucket_name) --recursive
aws s3 rm s3://$(terraform output -raw data_bucket_name) --recursive
terraform destroy -auto-approve
```
