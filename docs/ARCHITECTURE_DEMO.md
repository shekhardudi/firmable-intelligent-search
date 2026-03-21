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
│   │  │  │  Ingest Task  (one-off ECS run-task, GPU)        │      │     │   │
│   │  │  │  EC2 g4dn.xlarge spot (T4 GPU, 16 GB VRAM)      │      │     │   │
│   │  │  │  ASG 0→1 via capacity provider, scales back to 0 │      │     │   │
│   │  │  │  SentenceTransformer batch encoding (7 M records)│      │     │   │
│   │  │  └──────────────────────────────────────────────────┘      │     │   │
│   │  │                                                            │     │   │
│   │  └────────────────────────────────────────────────────────────┘     │   │
│   │                                                                     │   │
│   │  ┌──────────────────────┐   ┌────────────────────────────────┐      │   │
│   │  │  Amazon OpenSearch   │   │  ElastiCache (Redis OSS)       │      │   │
│   │  │  r6g.xlarge.search   │   │  cache.t4g.micro               │      │   │
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
| OpenSearch nodes      | 1 × r6g.xlarge (fp16 SQ)      | 3 × r6g.xlarge (fp16 SQ)          |
| ElastiCache nodes     | 1 × t4g.micro                 | 2 shards + 1 replica each         |
| ECS tasks             | 2–4 backend (auto-scaled)     | 4–20 backend                      |
| Auto-scaling          | CPU target-tracking at 60%    | CPU + p95 latency target tracking |
| TLS                   | CloudFront default cert       | ACM cert + Route 53               |
| Backup / snapshots    | None                          | Daily automated snapshots         |
| Container Insights    | Enabled (same as prod)        | Enabled                           |

## Quick-Start Steps

> **One-command deploy:** Run `./deploy-all.sh` from the repo root.
> It builds images, deploys infra, uploads data, deploys the frontend,
> and kicks off GPU-accelerated ingestion. Supports `--skip-infra`,
> `--skip-ingest`, and `--teardown` flags.

### Prerequisites

- AWS CLI v2 configured with credentials
- Docker running, Terraform, Node/npm, jq, python3
- `OPENAI_API_KEY` and `TAVILY_API_KEY` environment variables set

### Manual Steps (if not using deploy-all.sh)

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

# Data-pipeline (ingest — CUDA image, needs --platform linux/amd64 on Apple Silicon)
docker build --platform linux/amd64 -t firmable-ingest ./data-pipeline
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

# 5. Run data ingestion (GPU-accelerated via EC2 capacity provider)
cd ../infrastructure/terraform/demo
CLUSTER=$(terraform output -raw ecs_cluster_name)
TASK_DEF=$(terraform output -raw ingest_task_definition)
SUBNET=$(terraform output -json private_subnet_ids | jq -r '.[0]')
INGEST_SG=$(terraform output -raw ingest_gpu_sg_id)
CAPACITY_PROVIDER=$(terraform output -raw ingest_gpu_capacity_provider)

aws ecs run-task \
  --cluster $CLUSTER \
  --task-definition $TASK_DEF \
  --capacity-provider-strategy "capacityProvider=$CAPACITY_PROVIDER,weight=1,base=1" \
  --region $REGION \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$INGEST_SG],assignPublicIp=DISABLED}"

# The ASG launches a g4dn.xlarge spot instance (~2 min boot), runs ingestion
# (~30-60 min for 7M records on GPU), then scales back to 0 instances.

# 6. Warm up (run before the demo)
for q in "fintech startups sydney" "saas companies 50 to 200 employees" "mining companies australia"; do
  curl -s "https://$CF_URL/api/search?q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$q'))")" > /dev/null
done
echo "Demo ready → https://$CF_URL"
```

## Tear-Down (after demo)

```bash
# One-command teardown:
./deploy-all.sh --teardown

# Or manually:

# Stop compute only — data persists for next demo session
cd infrastructure/terraform/demo
CLUSTER=$(terraform output -raw ecs_cluster_name)
aws ecs update-service --cluster $CLUSTER --service firmable-demo-backend --desired-count 0

# Full destroy (handles versioned S3 buckets)
FRONTEND_BUCKET=$(terraform output -raw frontend_bucket_name)
DATA_BUCKET=$(terraform output -raw data_bucket_name)
aws s3 rm s3://$FRONTEND_BUCKET --recursive
aws s3 rm s3://$DATA_BUCKET --recursive

# Delete versioned objects (required if bucket versioning is enabled)
for BUCKET in $FRONTEND_BUCKET $DATA_BUCKET; do
  aws s3api list-object-versions --bucket $BUCKET \
    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json \
    | aws s3api delete-objects --bucket $BUCKET --delete file:///dev/stdin 2>/dev/null || true
  aws s3api list-object-versions --bucket $BUCKET \
    --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json \
    | aws s3api delete-objects --bucket $BUCKET --delete file:///dev/stdin 2>/dev/null || true
done

terraform destroy -auto-approve \
  -var='opensearch_password=MySecurePassword123!' \
  -var="openai_api_key=${OPENAI_API_KEY:-dummy}" \
  -var="tavily_api_key=${TAVILY_API_KEY:-dummy}" \
  -var="backend_image=dummy" \
  -var="ingest_image=dummy"
```
