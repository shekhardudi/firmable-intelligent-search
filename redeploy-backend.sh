#!/usr/bin/env bash
set -euo pipefail

CLUSTER="firmable-demo-cluster"
SERVICE="firmable-demo-backend"
REGION="ap-southeast-2"
REGISTRY="977688665146.dkr.ecr.${REGION}.amazonaws.com"
IMAGE="${REGISTRY}/firmable-backend:latest"

cd /Users/lucifer/Documents/ai-workspace/firmable-intelligent-search

echo "=== [1/5] ECR Login ==="
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

echo "=== [2/5] Docker Build ==="
docker build --platform linux/amd64 -t firmable-backend ./backend

echo "=== [3/5] Docker Push ==="
docker tag firmable-backend:latest "$IMAGE"
docker push "$IMAGE"

echo "=== [4/6] Register new task definition with updated image ==="
TASK_DEF_JSON=$(aws ecs describe-task-definition --task-definition "$SERVICE" \
  --region "$REGION" --query 'taskDefinition' --output json)
# Update the backend container image in the task definition
TMPFILE=$(mktemp /tmp/taskdef.XXXXXX.json)
echo "$TASK_DEF_JSON" | python3 -c "
import json, sys
td = json.load(sys.stdin)
for c in td['containerDefinitions']:
    if c['name'] == 'backend':
        c['image'] = '$IMAGE'
# Keep only the fields accepted by register-task-definition
keep = ['family','containerDefinitions','taskRoleArn','executionRoleArn',
        'networkMode','volumes','placementConstraints','requiresCompatibilities',
        'cpu','memory','runtimePlatform']
print(json.dumps({k: td[k] for k in keep if k in td}))
" > "$TMPFILE"
NEW_ARN=$(aws ecs register-task-definition \
  --cli-input-json "file://$TMPFILE" \
  --region "$REGION" --query 'taskDefinition.taskDefinitionArn' --output text)
rm -f "$TMPFILE"
echo "  Registered: $NEW_ARN"

echo "=== [5/6] Stopping running tasks ==="
TASKS=$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" \
  --region "$REGION" --query 'taskArns[]' --output text)
if [[ -n "$TASKS" && "$TASKS" != "None" ]]; then
  echo "$TASKS" | tr '\t' '\n' | while read -r ARN; do
    echo "  Stopping $ARN"
    aws ecs stop-task --cluster "$CLUSTER" --task "$ARN" --region "$REGION" --reason "redeploy" --output text --query 'task.lastStatus'
  done
else
  echo "  No running tasks to stop"
fi

echo "=== [6/6] Deploy new task definition ==="
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
  --task-definition "$NEW_ARN" --force-new-deployment --region "$REGION" \
  --query 'service.deployments[0].{status:status,desired:desiredCount,running:runningCount}' --output table

echo ""
echo "Deployment triggered. Waiting for service to stabilize..."
echo "(Ctrl+C to skip waiting — deployment will continue in the background)"
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE" --region "$REGION" && \
  echo "✅ Deploy complete — service stable" || \
  echo "⚠️  Timed out waiting, check ECS console"