# The Crawl Log — Runbook

Operations guide for maintaining the production deployment at https://crawl.sigilark.com

---

## Architecture Quick Reference

```
Internet → ALB (HTTPS) → ECS Fargate (1 vCPU, 2GB) → Container (uvicorn :8000)
                                                      ↳ DynamoDB (via VPC endpoint)
                                                      ↳ S3 (via VPC endpoint) → CloudFront CDN
                                                      ↳ Secrets Manager (API keys)
```

- **AWS Region:** us-east-1
- **Stack Name:** AchievementIntercomStack
- **Domain:** crawl.sigilark.com
- **CI/CD:** GitHub Actions → auto-deploy on push to main

---

## Checking Service Health

```bash
# Quick health check
curl https://crawl.sigilark.com/health

# ECS service status
aws ecs describe-services \
  --cluster $(aws ecs list-clusters --query 'clusterArns[0]' --output text) \
  --services $(aws ecs list-services --cluster $(aws ecs list-clusters --query 'clusterArns[0]' --output text) --query 'serviceArns[0]' --output text) \
  --query 'services[0].{status:status,desired:desiredCount,running:runningCount}'

# CloudFormation stack status
aws cloudformation describe-stacks --stack-name AchievementIntercomStack \
  --query 'Stacks[0].StackStatus' --output text
```

---

## Viewing Logs

```bash
# Find the log group
LOG_GROUP=$(aws logs describe-log-groups --log-group-name-prefix "Achievement" \
  --query 'logGroups[0].logGroupName' --output text)

# Latest log stream
STREAM=$(aws logs describe-log-streams --log-group-name "$LOG_GROUP" \
  --order-by LastEventTime --descending --limit 1 \
  --query 'logStreams[0].logStreamName' --output text)

# Tail recent logs
aws logs get-log-events --log-group-name "$LOG_GROUP" \
  --log-stream-name "$STREAM" --limit 50 \
  --query 'events[*].message' --output text
```

---

## Redeploying

### Via CI/CD (recommended)
Push to `main` — GitHub Actions handles lint, test, docker build, and deploy automatically.

```bash
git push origin main
# Monitor: gh run list --repo sigilark/dungeon-crawler-carl --limit 1
```

### Manual deploy (if CI is broken)
```bash
cd cdk
JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 cdk deploy \
  --context account=302654592899 \
  --context region=us-east-1 \
  --require-approval never
```

---

## Clearing Production Data

### Clear all achievements
```bash
# Scan and delete all items from DynamoDB
for id in $(aws dynamodb scan --table-name achievements \
  --query 'Items[*].id.N' --output text); do
  aws dynamodb delete-item --table-name achievements \
    --key "{\"id\": {\"N\": \"$id\"}}"
done
```

### Clear audio cache
```bash
# List the S3 bucket
BUCKET=$(aws cloudformation describe-stacks --stack-name AchievementIntercomStack \
  --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' --output text)

# Delete all audio files
aws s3 rm s3://$BUCKET --recursive
```

---

## Common Issues

### "Stack is in UPDATE_IN_PROGRESS"
A previous deploy is still running. Wait for it to complete or check:
```bash
aws cloudformation describe-stacks --stack-name AchievementIntercomStack \
  --query 'Stacks[0].StackStatus' --output text
```

### Container keeps restarting
Check logs for import errors or missing dependencies:
```bash
# Check recent ECS events
aws ecs describe-services --cluster <cluster> --services <service> \
  --query 'services[0].events[:5].[message]' --output text
```
Common causes: missing Python package in requirements.txt, missing system dep in Dockerfile.

### Audio not playing on mobile
Browser autoplay restrictions. The Play button should appear — if not, check the browser console for errors.

### ElevenLabs rate limit
The app makes 3 ElevenLabs calls per achievement (title, description, reward). If you hit rate limits, reduce generation frequency or upgrade your ElevenLabs plan.

### Reward format drift
Check if the model is clustering on specific reward formats:
```bash
curl https://crawl.sigilark.com/api/admin/reward-distribution
```
If any format exceeds 40%, consider reviewing the system prompt. Run `python scripts/check_reward_distribution.py --count 20` locally to validate with fresh samples.

### Daily challenge participation
Check how many users are engaging with the daily challenge:
```bash
curl https://crawl.sigilark.com/api/admin/daily-challenge
```

### Generator retry frequency
Check CloudWatch logs for banned content retries:
```bash
aws logs filter-log-events --log-group-name "$LOG_GROUP" \
  --filter-pattern "Banned content detected" --limit 20 \
  --query 'events[*].message' --output text
```
Zero retries is ideal (Streisand fix working). Frequent retries may indicate the prompt needs tuning.

### Claude API errors
Check if the API key is valid and has credits:
```bash
aws secretsmanager get-secret-value \
  --secret-id achievement-intercom/anthropic-api-key \
  --query 'SecretString' --output text | head -c 20
```

---

## Secrets Management

Secrets are stored in AWS Secrets Manager:
- `achievement-intercom/anthropic-api-key`
- `achievement-intercom/elevenlabs-api-key`
- `achievement-intercom/elevenlabs-voice-id`

### Rotate a secret
```bash
aws secretsmanager update-secret \
  --secret-id achievement-intercom/anthropic-api-key \
  --secret-string "new-key-here"
```
Then redeploy to pick up the new value (ECS pulls secrets at task start).

---

## Cost Monitoring

### Current monthly estimate: ~$42
- Fargate: ~$35
- ALB: ~$18
- DynamoDB/S3/CloudFront: ~$2
- Secrets Manager: ~$1.20
- Claude API: ~$3 (at ~10 achievements/day with Sonnet)
- ElevenLabs: ~$3

### Check current month spend
```bash
aws ce get-cost-and-usage \
  --time-period Start=$(date +%Y-%m-01),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY --metrics BlendedCost \
  --query 'ResultsByTime[0].Total.BlendedCost'
```

---

## Disaster Recovery

- **DynamoDB:** RemovalPolicy.RETAIN — survives stack deletion
- **S3 bucket:** RemovalPolicy.RETAIN — survives stack deletion
- **Secrets:** Not managed by CDK — persist independently
- **Code:** GitHub repo is the source of truth
- **Full rebuild:** `cdk deploy` recreates everything from scratch (pre-create secrets first)
