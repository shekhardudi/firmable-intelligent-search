#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Run GPU-accelerated data ingestion (g4dn.xlarge spot instance)
#
# Scales the ASG from 0 → 1. The instance boots, downloads pipeline code
# from S3, installs dependencies, runs ingestion, then self-terminates
# (scales ASG back to 0 and shuts down).
#
# Usage:
#   ./run-ingest-gpu.sh              # Launch ingestion
#   ./run-ingest-gpu.sh --status     # Check ASG / instance status
#   ./run-ingest-gpu.sh --stop       # Force scale ASG back to 0
# ---------------------------------------------------------------------------
set -euo pipefail

ASG_NAME="firmable-demo-ingest-gpu"
REGION="ap-southeast-2"

ACTION="${1:-start}"

status() {
  echo "=== ASG status ==="
  aws autoscaling describe-auto-scaling-groups \
    --auto-scaling-group-names "$ASG_NAME" \
    --region "$REGION" \
    --query 'AutoScalingGroups[0].{DesiredCapacity:DesiredCapacity,Instances:Instances[*].{Id:InstanceId,State:LifecycleState,Health:HealthStatus}}' \
    --output table
}

case "$ACTION" in
  --status|-s)
    status
    ;;

  --stop|-k)
    echo "Scaling ASG to 0 (terminating any running instance)..."
    aws autoscaling set-desired-capacity \
      --auto-scaling-group-name "$ASG_NAME" \
      --desired-capacity 0 \
      --region "$REGION"
    echo "Done. Instance will terminate shortly."
    ;;

  start|--start)
    # Check if already running
    CURRENT=$(aws autoscaling describe-auto-scaling-groups \
      --auto-scaling-group-names "$ASG_NAME" \
      --region "$REGION" \
      --query 'AutoScalingGroups[0].DesiredCapacity' --output text)

    if [[ "$CURRENT" -gt 0 ]]; then
      echo "Ingestion already running (desired_capacity=$CURRENT)."
      status
      exit 0
    fi

    echo "Scaling ASG to 1 — launching g4dn.xlarge spot instance..."
    aws autoscaling set-desired-capacity \
      --auto-scaling-group-name "$ASG_NAME" \
      --desired-capacity 1 \
      --region "$REGION"

    echo ""
    echo "Instance will boot (~2 min), install deps (~3 min), then ingest (~30-60 min)."
    echo "It self-terminates after completion."
    echo ""
    echo "Check status:  ./run-ingest-gpu.sh --status"
    echo "Force stop:    ./run-ingest-gpu.sh --stop"
    echo "Logs:          SSM Session Manager → /var/log/ingest.log"
    ;;

  *)
    echo "Usage: $0 [--start | --status | --stop]"
    exit 1
    ;;
esac
