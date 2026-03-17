#!/usr/bin/env bash
# ==========================================================================
# Firmable Demo — Full Teardown Script
# Cleanly destroys all AWS resources created by Terraform.
#
# Usage:
#   cd infrastructure/terraform/demo
#   chmod +x teardown.sh
#   ./teardown.sh                  # interactive — prompts before destroying
#   ./teardown.sh --auto-approve   # non-interactive — destroys immediately
# ==========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

AUTO_APPROVE=""
if [[ "${1:-}" == "--auto-approve" ]]; then
  AUTO_APPROVE="-auto-approve"
fi

echo "============================================"
echo " Firmable Demo — Teardown"
echo "============================================"
echo ""

# ------------------------------------------------------------------
# 1. Stop ECS services (speeds up destroy — tasks drain immediately)
# ------------------------------------------------------------------
echo "→ Scaling down ECS services..."
CLUSTER=$(terraform output -raw ecs_cluster_name 2>/dev/null || true)
if [[ -n "$CLUSTER" ]]; then
  aws ecs update-service \
    --cluster "$CLUSTER" \
    --service firmable-demo-backend \
    --desired-count 0 \
    --no-cli-pager 2>/dev/null || true
  echo "  ECS backend scaled to 0."
else
  echo "  (no cluster found — skipping)"
fi

# ------------------------------------------------------------------
# 2. Empty S3 buckets (Terraform cannot delete non-empty buckets)
# ------------------------------------------------------------------
echo "→ Emptying S3 buckets..."
BUCKET=$(terraform output -raw frontend_bucket_name 2>/dev/null || true)
if [[ -n "$BUCKET" ]]; then
  aws s3 rm "s3://$BUCKET" --recursive --no-cli-pager 2>/dev/null || true
  echo "  Emptied s3://$BUCKET"
else
  echo "  (no frontend bucket found — skipping)"
fi

# ------------------------------------------------------------------
# 3. Invalidate CloudFront cache (avoid stale edge content)
# ------------------------------------------------------------------
echo "→ Disabling CloudFront distribution..."
# CloudFront distributions must be disabled before deletion.
# Terraform handles this, but it can take a few minutes.
echo "  (Terraform will handle CloudFront disable + delete)"

# ------------------------------------------------------------------
# 4. Terraform destroy
# ------------------------------------------------------------------
echo ""
echo "→ Running terraform destroy..."
echo ""

if [[ -n "$AUTO_APPROVE" ]]; then
  terraform destroy $AUTO_APPROVE
else
  echo "This will PERMANENTLY DELETE all demo infrastructure."
  echo ""
  terraform destroy
fi

# ------------------------------------------------------------------
# 5. Clean up local state files (optional)
# ------------------------------------------------------------------
echo ""
echo "→ Cleaning local Terraform files..."
rm -rf .terraform/providers 2>/dev/null || true
rm -f terraform.tfstate.backup 2>/dev/null || true
echo "  Removed cached providers and backup state."

# ------------------------------------------------------------------
# 6. Optionally delete ECR repository
# ------------------------------------------------------------------
echo ""
echo "→ Checking for ECR repository..."
ECR_REPO="firmable-backend"
if aws ecr describe-repositories --repository-names "$ECR_REPO" --no-cli-pager 2>/dev/null; then
  if [[ -n "$AUTO_APPROVE" ]]; then
    aws ecr delete-repository --repository-name "$ECR_REPO" --force --no-cli-pager
    echo "  Deleted ECR repository: $ECR_REPO"
  else
    read -rp "  Delete ECR repository '$ECR_REPO'? (y/N) " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
      aws ecr delete-repository --repository-name "$ECR_REPO" --force --no-cli-pager
      echo "  Deleted ECR repository: $ECR_REPO"
    else
      echo "  Kept ECR repository."
    fi
  fi
else
  echo "  (no ECR repository found — skipping)"
fi

echo ""
echo "============================================"
echo " Teardown complete."
echo "============================================"
