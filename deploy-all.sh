#!/usr/bin/env bash
# ===========================================================================
# deploy-all.sh — Full end-to-end deployment for Firmable Intelligent Search
#
# Builds images, deploys infra, uploads data, deploys frontend, and kicks
# off GPU-accelerated data ingestion (g4dn.xlarge spot instance).
#
# Prerequisites:
#   - AWS CLI v2 configured with correct credentials
#   - Docker running
#   - terraform, node/npm, jq, python3 installed
#   - Environment variables set: OPENAI_API_KEY, TAVILY_API_KEY
#
# Usage:
#   ./deploy-all.sh                  # Deploy everything
#   ./deploy-all.sh --skip-infra     # Skip terraform (images + frontend + ingest only)
#   ./deploy-all.sh --skip-ingest    # Deploy everything except data ingestion
#   ./deploy-all.sh --teardown       # Tear down all resources
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="ap-southeast-2"
OPENSEARCH_PASSWORD='MySecurePassword123!'

# ── Flags ──────────────────────────────────────────────────────────────────
SKIP_INFRA=false
SKIP_INGEST=false
TEARDOWN=false

for arg in "$@"; do
  case "$arg" in
    --skip-infra)  SKIP_INFRA=true ;;
    --skip-ingest) SKIP_INGEST=true ;;
    --teardown)    TEARDOWN=true ;;
    *) echo "Unknown flag: $arg"; exit 1 ;;
  esac
done

# ── Validate env vars ─────────────────────────────────────────────────────
if [[ "$TEARDOWN" == false ]]; then
  : "${OPENAI_API_KEY:?Set OPENAI_API_KEY before running}"
  : "${TAVILY_API_KEY:?Set TAVILY_API_KEY before running}"
fi

ACCOUNT=$(aws sts get-caller-identity --query Account --output text --region "$REGION")
REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
TF_DIR="${SCRIPT_DIR}/infrastructure/terraform/demo"

# ── Helper ─────────────────────────────────────────────────────────────────
step() { echo -e "\n\033[1;36m▸ $1\033[0m"; }

# ===========================================================================
# TEARDOWN
# ===========================================================================
if [[ "$TEARDOWN" == true ]]; then
  step "Tearing down all resources..."
  cd "$TF_DIR"

  CLUSTER=$(terraform output -raw ecs_cluster_name 2>/dev/null || true)
  if [[ -n "$CLUSTER" ]]; then
    step "Scaling backend service to 0"
    aws ecs update-service --cluster "$CLUSTER" --service firmable-demo-backend \
      --desired-count 0 --region "$REGION" >/dev/null 2>&1 || true
  fi

  step "Emptying S3 buckets"
  FRONTEND_BUCKET=$(terraform output -raw frontend_bucket_name 2>/dev/null || true)
  DATA_BUCKET=$(terraform output -raw data_bucket_name 2>/dev/null || true)
  [[ -n "$FRONTEND_BUCKET" ]] && aws s3 rm "s3://${FRONTEND_BUCKET}" --recursive --region "$REGION" 2>/dev/null || true
  [[ -n "$DATA_BUCKET" ]]     && aws s3 rm "s3://${DATA_BUCKET}" --recursive --region "$REGION" 2>/dev/null || true

  # Handle versioned buckets (avoids BucketNotEmpty error)
  for BUCKET in "$FRONTEND_BUCKET" "$DATA_BUCKET"; do
    [[ -z "$BUCKET" ]] && continue
    VERSIONS=$(aws s3api list-object-versions --bucket "$BUCKET" --region "$REGION" \
      --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json 2>/dev/null || echo '{"Objects":null}')
    if [[ $(echo "$VERSIONS" | jq '.Objects // [] | length') -gt 0 ]]; then
      echo "$VERSIONS" | aws s3api delete-objects --bucket "$BUCKET" --region "$REGION" \
        --delete file:///dev/stdin 2>/dev/null || true
    fi
    DELETE_MARKERS=$(aws s3api list-object-versions --bucket "$BUCKET" --region "$REGION" \
      --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json 2>/dev/null || echo '{"Objects":null}')
    if [[ $(echo "$DELETE_MARKERS" | jq '.Objects // [] | length') -gt 0 ]]; then
      echo "$DELETE_MARKERS" | aws s3api delete-objects --bucket "$BUCKET" --region "$REGION" \
        --delete file:///dev/stdin 2>/dev/null || true
    fi
  done

  step "Terraform destroy"
  terraform destroy -auto-approve \
    -var="opensearch_password=${OPENSEARCH_PASSWORD}" \
    -var="openai_api_key=${OPENAI_API_KEY:-dummy}" \
    -var="tavily_api_key=${TAVILY_API_KEY:-dummy}" \
    -var="backend_image=dummy"

  echo -e "\n\033[1;32m✓ Teardown complete.\033[0m"
  exit 0
fi

# ===========================================================================
# STEP 1 — Build and push Docker images
# ===========================================================================
step "1/6  Creating ECR repository (if needed)"
aws ecr create-repository --repository-name firmable-backend --region "$REGION" 2>/dev/null || true

step "1/6  Logging in to ECR"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

step "1/6  Building & pushing backend image"
docker build -t firmable-backend "${SCRIPT_DIR}/backend"
docker tag firmable-backend:latest "${REGISTRY}/firmable-backend:latest"
docker push "${REGISTRY}/firmable-backend:latest"

# ===========================================================================
# STEP 2 — Deploy infrastructure with Terraform
# ===========================================================================
if [[ "$SKIP_INFRA" == false ]]; then
  step "2/6  Terraform init + apply"
  cd "$TF_DIR"
  terraform init -input=false
  terraform apply -auto-approve \
    -var="backend_image=${REGISTRY}/firmable-backend:latest" \
    -var="opensearch_password=${OPENSEARCH_PASSWORD}" \
    -var="openai_api_key=${OPENAI_API_KEY}" \
    -var="tavily_api_key=${TAVILY_API_KEY}"
fi

# ===========================================================================
# STEP 3 — Upload data and pipeline code to S3
# ===========================================================================
cd "$TF_DIR"
step "3/6  Uploading companies_sorted.csv to S3"
DATA_BUCKET=$(terraform output -raw data_bucket_name)
aws s3 cp "${SCRIPT_DIR}/data-pipeline/companies_sorted.csv" \
  "s3://${DATA_BUCKET}/companies_sorted.csv" --region "$REGION"

step "3/6  Packaging and uploading data-pipeline code to S3"
tar -czf /tmp/data-pipeline.tar.gz -C "${SCRIPT_DIR}/data-pipeline" \
  data_ingestion_pipeline.py observability.py ingest_config.yaml \
  index_mapping.json requirements.txt country_taxonomy.json industry_taxonomy.json
aws s3 cp /tmp/data-pipeline.tar.gz "s3://${DATA_BUCKET}/data-pipeline.tar.gz" --region "$REGION"
rm -f /tmp/data-pipeline.tar.gz

# ===========================================================================
# STEP 4 — Build and deploy frontend SPA
# ===========================================================================
step "4/6  Building frontend"
FRONTEND_BUCKET=$(terraform output -raw frontend_bucket_name)
CF_URL=$(terraform output -raw cloudfront_url)

cd "${SCRIPT_DIR}/frontend"
npm ci --prefer-offline
VITE_API_URL="https://${CF_URL}" npm run build
aws s3 sync dist/ "s3://${FRONTEND_BUCKET}/" --delete --region "$REGION"

# Invalidate CloudFront cache
CF_DIST_ID=$(aws cloudfront list-distributions --region "$REGION" \
  --query "DistributionList.Items[?Origins.Items[?DomainName=='${FRONTEND_BUCKET}.s3.${REGION}.amazonaws.com']].Id" \
  --output text 2>/dev/null || true)
if [[ -n "$CF_DIST_ID" && "$CF_DIST_ID" != "None" ]]; then
  step "4/6  Invalidating CloudFront cache"
  aws cloudfront create-invalidation --distribution-id "$CF_DIST_ID" --paths "/*" >/dev/null
fi

# ===========================================================================
# STEP 5 — Trigger GPU-accelerated data ingestion
# ===========================================================================
if [[ "$SKIP_INGEST" == false ]]; then
  step "5/6  Triggering GPU data ingestion (scaling ASG to 1)"
  cd "$TF_DIR"

  ASG_NAME=$(terraform output -raw ingest_gpu_asg_name)
  aws autoscaling set-desired-capacity \
    --auto-scaling-group-name "$ASG_NAME" \
    --desired-capacity 1 \
    --region "$REGION"

  echo "  ASG:  $ASG_NAME → desired_capacity=1"
  echo ""
  echo "  A g4dn.xlarge spot instance will boot (~2 min), install deps (~3 min),"
  echo "  then ingest ~6.5M records with GPU acceleration (~30-60 min)."
  echo "  The instance self-terminates after completion."
  echo ""
  echo "  Monitor: aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names $ASG_NAME --region $REGION --query 'AutoScalingGroups[0].Instances'"
  echo "  Logs:    SSM → /var/log/ingest.log or connect via Session Manager"
else
  step "5/6  Skipping data ingestion (--skip-ingest)"
fi

# ===========================================================================
# STEP 6 — Warm up search
# ===========================================================================
step "6/6  Warming up search (3 queries)"
cd "$TF_DIR"
CF_URL=$(terraform output -raw cloudfront_url)
for q in "fintech startups sydney" "saas companies 50 to 200 employees" "mining companies australia"; do
  ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$q'))")
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://${CF_URL}/api/search?q=${ENCODED}" || true)
  echo "  ${q} → HTTP ${HTTP_CODE}"
done

# ===========================================================================
# Done
# ===========================================================================
echo ""
echo -e "\033[1;32m✓ Deployment complete!\033[0m"
echo ""
echo "  Demo URL:  https://${CF_URL}"
echo "  API:       https://${CF_URL}/api/search?q=tech+companies+in+australia"
echo ""
if [[ "$SKIP_INGEST" == false ]]; then
  echo "  ⚠  Data ingestion is running on a GPU instance in the background."
  echo "     Wait for it to finish before demoing. Check status with:"
  echo "     aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names $(cd $TF_DIR && terraform output -raw ingest_gpu_asg_name) --region $REGION --query 'AutoScalingGroups[0].Instances'"
fi
