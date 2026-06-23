#!/bin/bash
# =============================================================================
# Football Cup — CloudShell Deploy Script
#
# WHERE EACH STEP RUNS:
#   CloudShell → CDK deploys, backend Docker build/push, all AWS CLI calls
#   CodeBuild  → coach ARM64 image only (triggered + polled from here)
#
# HOW TO USE (in AWS CloudShell, us-east-1):
#   git clone https://github.com/AbilashEG/football-cup.git
#   cd football-cup
#   chmod +x deploy-cloudshell.sh
#   ./deploy-cloudshell.sh
# =============================================================================
set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --no-cli-pager)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "=============================================="
echo " Football Cup — CloudShell Deployment"
echo " Coach image  → CodeBuild (ARM64 native)"
echo " Everything else → CloudShell"
echo "=============================================="
echo " Account : $ACCOUNT_ID"
echo " Region  : $REGION"
echo " Time    : $TIMESTAMP"
echo "=============================================="

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1: CDK base stacks (CloudShell — no Docker needed)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 1 — CDK base stacks (CloudShell)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd infra
pip install -r requirements.txt --quiet --upgrade
npm install -g aws-cdk --quiet 2>/dev/null || true
cdk bootstrap "aws://$ACCOUNT_ID/$REGION" --quiet 2>/dev/null || true

cdk deploy \
  FootballStorageStack \
  FootballAgentCoreStack \
  FootballCodeBuildStack \
  FootballMcpToolsStack \
  FootballGatewayStack \
  --require-approval never \
  --context "account=$ACCOUNT_ID" \
  --no-cli-pager 2>/dev/null || true

echo "✓ Base stacks deployed"
cd ..

COACH_REPO=$(aws ssm get-parameter \
  --name "/football-cup/coach/ecr_repo_uri" \
  --query Parameter.Value --output text --region "$REGION" --no-cli-pager)

RUNTIME_ROLE=$(aws ssm get-parameter \
  --name "/football-cup/coach/runtime_role_arn" \
  --query Parameter.Value --output text --region "$REGION" --no-cli-pager)

CB_PROJECT=$(aws ssm get-parameter \
  --name "/football-cup/codebuild/coach_project_name" \
  --query Parameter.Value --output text --region "$REGION" --no-cli-pager)

echo "  Coach ECR        : $COACH_REPO"
echo "  Runtime Role     : $RUNTIME_ROLE"
echo "  CodeBuild project: $CB_PROJECT"

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: CodeBuild — ARM64 coach image
# ✅ curl -L download inside CodeBuild buildspec (NOT git clone)
# ✅ GitHub: AbilashEG (one E)
# ✅ --no-cli-pager on all aws cli calls
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 2 — Coach ARM64 image (CodeBuild)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

BUILD_ID=$(aws codebuild start-build \
  --project-name "$CB_PROJECT" \
  --region "$REGION" \
  --no-cli-pager \
  --query "build.id" \
  --output text)

echo "  Build ID: $BUILD_ID"
echo "  Logs: https://$REGION.console.aws.amazon.com/cloudwatch/home?region=$REGION#logsV2:log-groups/log-group/%2Faws%2Fcodebuild%2Ffootball-cup-coach-build"

echo "  Polling CodeBuild (~5-8 min for ARM64 image)..."
ELAPSED=0
while [ $ELAPSED -lt 900 ]; do
  STATUS=$(aws codebuild batch-get-builds \
    --ids "$BUILD_ID" \
    --region "$REGION" \
    --no-cli-pager \
    --query "builds[0].buildStatus" \
    --output text)

  PHASE=$(aws codebuild batch-get-builds \
    --ids "$BUILD_ID" \
    --region "$REGION" \
    --no-cli-pager \
    --query "builds[0].currentPhase" \
    --output text)

  printf "  [%3ds] %-12s  %s\n" "$ELAPSED" "$STATUS" "$PHASE"

  if [ "$STATUS" = "SUCCEEDED" ]; then
    echo "  ✓ CodeBuild succeeded — ARM64 coach image in ECR"
    break
  elif [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "STOPPED" ] || [ "$STATUS" = "TIMED_OUT" ]; then
    echo "  ✗ CodeBuild $STATUS"
    echo "  Check logs above ↑"
    exit 1
  fi

  sleep 15
  ELAPSED=$((ELAPSED + 15))
done

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: Backend Docker image (CloudShell Docker + buildx)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 3 — Backend Docker image (CloudShell)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker run --privileged --rm tonistiigi/binfmt --install arm64 2>/dev/null || true
docker buildx inspect football-cup-builder 2>/dev/null \
  || docker buildx create --name football-cup-builder --use --driver docker-container
docker buildx use football-cup-builder

# Deploy BackendStack first to get ECR repo created
cd infra
cdk deploy FootballBackendStack \
  --require-approval never \
  --context "account=$ACCOUNT_ID"
cd ..

BACKEND_REPO=$(aws ssm get-parameter \
  --name "/football-cup/backend/ecr_repo_uri" \
  --query Parameter.Value --output text --region "$REGION" --no-cli-pager)

echo "  Backend ECR: $BACKEND_REPO"

ECR_REGISTRY=$(echo "$COACH_REPO" | cut -d'/' -f1)
aws ecr get-login-password --region "$REGION" --no-cli-pager \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

docker buildx build \
  --platform linux/arm64 \
  --file backend/Dockerfile \
  --tag "$BACKEND_REPO:latest" \
  --tag "$BACKEND_REPO:$TIMESTAMP" \
  --push \
  .

echo "  ✓ Backend image pushed: $BACKEND_REPO:latest"

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4: Create AgentCore Runtime (1 runtime — football-coach only)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 4 — AgentCore Runtime"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

GK_FN=$(aws ssm get-parameter    --name "/football-cup/players/goalkeeper/function_name"     --query Parameter.Value --output text --region "$REGION" --no-cli-pager)
DEF_L_FN=$(aws ssm get-parameter --name "/football-cup/players/defender_left/function_name"  --query Parameter.Value --output text --region "$REGION" --no-cli-pager)
DEF_R_FN=$(aws ssm get-parameter --name "/football-cup/players/defender_right/function_name" --query Parameter.Value --output text --region "$REGION" --no-cli-pager)
MID_FN=$(aws ssm get-parameter   --name "/football-cup/players/midfielder/function_name"     --query Parameter.Value --output text --region "$REGION" --no-cli-pager)
STR_FN=$(aws ssm get-parameter   --name "/football-cup/players/striker/function_name"        --query Parameter.Value --output text --region "$REGION" --no-cli-pager)

echo "  GK=$GK_FN  DEF_L=$DEF_L_FN  DEF_R=$DEF_R_FN  MID=$MID_FN  STR=$STR_FN"

# Check for existing runtime
EXISTING_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
  --region "$REGION" --no-cli-pager \
  --query "agentRuntimes[?agentRuntimeName=='football-coach'].agentRuntimeId" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_ID" ] && [ "$EXISTING_ID" != "None" ] && [ "$EXISTING_ID" != "" ]; then
  echo "  Existing runtime $EXISTING_ID — updating image + env vars..."

  aws bedrock-agentcore-control update-agent-runtime \
    --agent-runtime-id "$EXISTING_ID" \
    --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${COACH_REPO}:latest\"}}" \
    --role-arn "$RUNTIME_ROLE" \
    --network-configuration '{"networkMode":"PUBLIC"}' \
    --environment-variables "{\"AGENTCORE_GATEWAY_URL\":\"\",\"AGENT_RUNTIME_ARN\":\"\",\"AWS_REGION\":\"${REGION}\"}" \
    --region "$REGION" --no-cli-pager

  RUNTIME_ENDPOINT=$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$EXISTING_ID" \
    --query "agentRuntimeEndpoint" --output text \
    --region "$REGION" --no-cli-pager)

  RUNTIME_ARN=$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$EXISTING_ID" \
    --query "agentRuntimeArn" --output text \
    --region "$REGION" --no-cli-pager)

  echo "  ✓ Runtime updated"
else
  echo "  Creating new runtime: football-coach..."

  RESPONSE=$(aws bedrock-agentcore-control create-agent-runtime \
    --agent-runtime-name "football-coach" \
    --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${COACH_REPO}:latest\"}}" \
    --network-configuration '{"networkMode":"PUBLIC"}' \
    --role-arn "$RUNTIME_ROLE" \
    --lifecycle-configuration '{"idleRuntimeSessionTimeout":300,"maxLifetime":900}' \
    --environment-variables "{\"AWS_REGION\":\"${REGION}\"}" \
    --region "$REGION" --no-cli-pager)

  RUNTIME_ENDPOINT=$(echo "$RESPONSE" | jq -r '.agentRuntimeEndpoint')
  RUNTIME_ARN=$(echo "$RESPONSE" | jq -r '.agentRuntimeArn')
  echo "  ✓ Runtime created — ARN: $RUNTIME_ARN"
fi

echo "  Endpoint: $RUNTIME_ENDPOINT"

# Store endpoint for backend
aws ssm put-parameter \
  --name "/football-cup/coach/agentcore_endpoint" \
  --value "${RUNTIME_ENDPOINT}/invocations" \
  --type String --overwrite \
  --region "$REGION" --no-cli-pager

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5: Create AgentCore Gateway + register 11 tools
# Then update runtime with AGENTCORE_GATEWAY_URL + AGENT_RUNTIME_ARN
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 5 — AgentCore Gateway (11 tools)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for existing Gateway
EXISTING_GW=$(aws bedrock-agentcore-control list-gateways \
  --region "$REGION" --no-cli-pager \
  --query "gateways[?name=='football-cup-gateway'].gatewayId" \
  --output text 2>/dev/null || echo "")

if [ -z "$EXISTING_GW" ] || [ "$EXISTING_GW" = "None" ]; then
  echo "  Creating Gateway: football-cup-gateway..."
  GW_RESPONSE=$(aws bedrock-agentcore-control create-gateway \
    --name "football-cup-gateway" \
    --protocol-type MCP \
    --role-arn "$RUNTIME_ROLE" \
    --region "$REGION" --no-cli-pager)
  GATEWAY_ID=$(echo "$GW_RESPONSE" | jq -r '.gatewayId')
  echo "  ✓ Gateway created: $GATEWAY_ID"
else
  GATEWAY_ID=$EXISTING_GW
  echo "  Using existing Gateway: $GATEWAY_ID"
fi

# Get Gateway MCP endpoint URL
GW_DETAIL=$(aws bedrock-agentcore-control get-gateway \
  --gateway-identifier "$GATEWAY_ID" \
  --region "$REGION" --no-cli-pager)
GATEWAY_URL=$(echo "$GW_DETAIL" | jq -r '.gatewayUrl // .mcpEndpoint // ""')

echo "  Gateway URL: $GATEWAY_URL"

# Register all 11 tools
TOOL_NAMES=$(aws ssm get-parameter \
  --name "/football-cup/gateway/tool_names" \
  --query Parameter.Value --output text --region "$REGION" --no-cli-pager)

echo "  Registering tools..."
IFS=',' read -ra TOOLS <<< "$TOOL_NAMES"
for TOOL_NAME in "${TOOLS[@]}"; do
  TOOL_ARN=$(aws ssm get-parameter \
    --name "/football-cup/gateway/lambda_arns/${TOOL_NAME}" \
    --query Parameter.Value --output text \
    --region "$REGION" --no-cli-pager 2>/dev/null || echo "")

  if [ -n "$TOOL_ARN" ] && [ "$TOOL_ARN" != "NOT_FOUND" ]; then
    aws bedrock-agentcore-control create-gateway-target \
      --gateway-identifier "$GATEWAY_ID" \
      --name "$TOOL_NAME" \
      --target-configuration "{\"lambdaConfiguration\":{\"lambdaArn\":\"${TOOL_ARN}\"}}" \
      --region "$REGION" --no-cli-pager 2>/dev/null && echo "  ✓ $TOOL_NAME" || echo "  ~ $TOOL_NAME (already exists)"
  fi
done

# Store Gateway URL in SSM
aws ssm put-parameter \
  --name "/football-cup/gateway/endpoint" \
  --value "$GATEWAY_URL" \
  --type String --overwrite \
  --region "$REGION" --no-cli-pager

# Update runtime with AGENTCORE_GATEWAY_URL + AGENT_RUNTIME_ARN now that both exist
echo "  Updating runtime env with Gateway URL + Runtime ARN..."
aws bedrock-agentcore-control update-agent-runtime \
  --agent-runtime-id "$EXISTING_ID" \
  --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${COACH_REPO}:latest\"}}" \
  --role-arn "$RUNTIME_ROLE" \
  --network-configuration '{"networkMode":"PUBLIC"}' \
  --environment-variables "{\"AGENTCORE_GATEWAY_URL\":\"${GATEWAY_URL}\",\"AGENT_RUNTIME_ARN\":\"${RUNTIME_ARN}\",\"AWS_REGION\":\"${REGION}\"}" \
  --region "$REGION" --no-cli-pager
echo "  ✓ Runtime env updated with Gateway URL"

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 6: Backend + Frontend env
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 6 — Backend CDK deploy"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd infra
cdk deploy FootballBackendStack \
  --require-approval never \
  --context "account=$ACCOUNT_ID"
cd ..

API_URL=$(aws ssm get-parameter --name "/football-cup/backend/api_url"  --query Parameter.Value --output text --region "$REGION" --no-cli-pager 2>/dev/null || echo "")
WS_URL=$(aws ssm get-parameter  --name "/football-cup/backend/ws_url"   --query Parameter.Value --output text --region "$REGION" --no-cli-pager 2>/dev/null || echo "")

cat > frontend/.env.local << EOF
NEXT_PUBLIC_API_URL=${API_URL}
NEXT_PUBLIC_WS_URL=${WS_URL}
NEXT_PUBLIC_REGION=${REGION}
NEXT_PUBLIC_AGENTCORE_ENDPOINT=${RUNTIME_ENDPOINT}/invocations
EOF
echo "✓ frontend/.env.local written"

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo " Deploy Complete ✓"
echo "=============================================="
echo "  Coach /health  : ${RUNTIME_ENDPOINT}/health"
echo "  Gateway URL    : ${GATEWAY_URL}"
if [ -n "$API_URL" ]; then
echo "  Backend API    : ${API_URL}"
echo "  WebSocket      : ${WS_URL}"
fi
echo ""
echo " Verify coach:"
echo "   curl ${RUNTIME_ENDPOINT}/health"
echo ""
echo " Check CodeBuild logs:"
echo "   aws logs get-log-events \\"
echo "     --log-group-name /aws/codebuild/football-cup-coach-build \\"
echo "     --log-stream-name <stream-name> \\"
echo "     --region $REGION --no-cli-pager \\"
echo "     --query 'events[*].message' --output text | tail -40"
echo ""
echo " Frontend (local):"
echo "   cd frontend && npm install && npm run dev"
echo "=============================================="
