#!/usr/bin/env bash
set -euo pipefail

REGION="ap-southeast-2"
S3_BUCKET="firmable-demo-frontend-977688665146"
CLOUDFRONT_ID="E1XM0R6TKFSSL1"
API_URL="https://dxsy9o0o1tb37.cloudfront.net"

cd /Users/lucifer/Documents/ai-workspace/firmable-intelligent-search/frontend

echo "=== [1/4] Install dependencies ==="
npm install

echo "=== [2/4] Build ==="
VITE_API_URL="$API_URL" npm run build

echo "=== [3/4] Sync to S3 ==="
aws s3 sync dist/ "s3://${S3_BUCKET}/" --delete --region "$REGION"

echo "=== [4/4] Invalidate CloudFront cache ==="
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id "$CLOUDFRONT_ID" \
  --paths "/*" \
  --query 'Invalidation.Id' --output text)
echo "  Invalidation: $INVALIDATION_ID"

echo ""
echo "✅ Frontend deployed to https://dxsy9o0o1tb37.cloudfront.net"
