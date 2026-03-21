# 1. Get instance ID (ingest instance must be running)
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names firmable-demo-ingest-gpu \
  --region ap-southeast-2 \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' --output text)

# 2. Get OpenSearch endpoint
OS_ENDPOINT=$(aws opensearch describe-domain \
  --domain-name firmable-demo-search \
  --region ap-southeast-2 \
  --query 'DomainStatus.Endpoints.vpc' --output text)

echo "Forwarding to $OS_ENDPOINT via $INSTANCE_ID"

# 3. Start port forward (maps localhost:9200 → OpenSearch:443 through the instance)
aws ssm start-session \
  --target "$INSTANCE_ID" \
  --region ap-southeast-2 \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$OS_ENDPOINT\"],\"portNumber\":[\"443\"],\"localPortNumber\":[\"9200\"]}"

  # OpenSearch Dashboards UI
open "https://localhost:9200/_dashboards"

# Or check doc count
curl -sk -u 'firmable:MySecurePassword123!' "https://localhost:9200/companies/_count" | python3 -m json.tool
