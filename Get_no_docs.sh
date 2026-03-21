# Get the instance ID
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names firmable-demo-ingest-gpu \
  --region ap-southeast-2 \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' --output text)

# Get OpenSearch endpoint
OS_ENDPOINT=$(aws opensearch describe-domain \
  --domain-name firmable-demo-search \
  --region ap-southeast-2 \
  --query 'DomainStatus.Endpoints.vpc' --output text)

# Run count query via SSM
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"curl -s -u firmable:'MySecurePassword123!' https://${OS_ENDPOINT}/companies/_count | python3 -m json.tool\"]" \
  --region ap-southeast-2 \
  --query 'Command.CommandId' --output text

  # Replace COMMAND_ID with the output from above
aws ssm get-command-invocation \
  --command-id COMMAND_ID \
  --instance-id "$INSTANCE_ID" \
  --region ap-southeast-2 \
  --query 'StandardOutputContent' --output text



  