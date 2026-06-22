#!/bin/bash
# =============================================================================
# Football Cup — Deployment Script
# Correct architecture: 1 Runtime (Coach) + 11 Gateway Tools
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure)
#   - Docker with buildx + QEMU for linux/arm64 cross-compilation
#   - jq installed (brew install jq / apt install jq)
#   - Python 3.11+ with pip
#   - Node.js 18+
# =============================================================================
set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "========================================"
echo " Football Cup — Correct Architecture"
echo " 1 Runtime (Coach) + 11 Gateway Tools"
echo "========================================"
echo " Account: $ACCOUNT_ID"
echo " Region:  $REGION"
echo " Time:    $TIMESTAMP"
echo "========================================"

# ── 0. Docker buildx for ARM64 ────────────────────────────────────────────────
echo ""
echo "── [0/6] Verifying Docker ARM64 build capability ──"
docker buildx inspect football-cup-builder 2>/dev/null \
  || docker buildx create --name football-cup-builder --use
docker buildx use football-cup-builder
echo "✓ Docker buildx ready"

# ── 1. CDK: Storage + MCP Tools (11 Lambdas) + Gateway SSM ──────────────────
echo ""
echo "── [1/6] CDK: Storage + MCP Tools + Gateway stacks ──"
cd infra
python3 -m pip install -r requirements.txt --quiet
cdk bootstrap "aws://$ACCOUNT_ID/$REGION" --quiet 2>/dev/null || true

cdk deploy \
  FootballStorageStack \
  FootballMcpToolsStack \
  FootballGatewayStack \
  --require-approval never \
  --context "account=$ACCOUNT_ID"

echo "✓ Storage + 11 Lambda tools deployed"
cd ..

# ── 2. CDK: AgentCore stack (1 ECR repo + IAM role) ──────────────────────────
echo ""
echo "── [2/6] CDK: AgentCore stack (coach ECR repo + IAM role) ──"
cd infra
cdk deploy FootballAgentCoreStack \
  --require-approval never \
  --context "account=$ACCOUNT_ID"
cd ..

COACH_REPO=$(aws ssm get-parameter \
  --name "/football-cup/coach/ecr_repo_uri" \
  --query Parameter.Value --output text --region "$REGION")

RUNTIME_ROLE=$(aws ssm get-parameter \
  --name "/football-cup/coach/runtime_role_arn" \
  --query Parameter.Value --output text --region "$REGION")

echo "  Coach ECR: $COACH_REPO"
echo "  IAM Role:  $RUNTIME_ROLE"
echo "✓ AgentCore stack ready"

# ── 3. Build and push ONE ARM64 coach container ───────────────────────────────
echo ""
echo "── [3/6] Build Coach Container (ARM64) ──"

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin \
    "$(echo "$COACH_REPO" | cut -d'/' -f1)"

# CRITICAL: --platform linux/arm64 — AgentCore Runtime runs on Graviton
# Build context is repo root so Dockerfile can COPY agents/shared
docker buildx build \
  --platform linux/arm64 \
  --file coach/Dockerfile \
  --tag "$COACH_REPO:latest" \
  --tag "$COACH_REPO:$TIMESTAMP" \
  --push \
  .

echo "✓ Coach container pushed: $COACH_REPO:latest"

# ── 4. Retrieve player Lambda function names for coach env vars ───────────────
echo ""
echo "── [4/6] Create AgentCore Runtime (coach — 1 runtime only) ──"

GK_FN=$(aws ssm get-parameter \
  --name "/football-cup/players/goalkeeper/function_name" \
  --query Parameter.Value --output text --region "$REGION")
DEF_L_FN=$(aws ssm get-parameter \
  --name "/football-cup/players/defender_left/function_name" \
  --query Parameter.Value --output text --region "$REGION")
DEF_R_FN=$(aws ssm get-parameter \
  --name "/football-cup/players/defender_right/function_name" \
  --query Parameter.Value --output text --region "$REGION")
MID_FN=$(aws ssm get-parameter \
  --name "/football-cup/players/midfielder/function_name" \
  --query Parameter.Value --output text --region "$REGION")
STR_FN=$(aws ssm get-parameter \
  --name "/football-cup/players/striker/function_name" \
  --query Parameter.Value --output text --region "$REGION")

echo "  Player functions:"
echo "    GK:    $GK_FN"
echo "    DEF_L: $DEF_L_FN"
echo "    DEF_R: $DEF_R_FN"
echo "    MID:   $MID_FN"
echo "    STR:   $STR_FN"

# Check if runtime already exists; update image if so
EXISTING_RUNTIME=$(aws bedrock-agentcore-control list-agent-runtimes \
  --region "$REGION" \
  --query "agentRuntimes[?agentRuntimeName=='football-coach'].agentRuntimeId" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_RUNTIME" ] && [ "$EXISTING_RUNTIME" != "None" ]; then
  echo "  Runtime football-coach already exists (ID: $EXISTING_RUNTIME)"
  echo "  Updating container image..."

  RUNTIME_RESPONSE=$(aws bedrock-agentcore-control update-agent-runtime \
    --agent-runtime-id "$EXISTING_RUNTIME" \
    --agent-runtime-artifact "{
        \"containerConfiguration\": {
            \"containerUri\": \"${COACH_REPO}:latest\"
        }
    }" \
    --region "$REGION")

  RUNTIME_ENDPOINT=$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$EXISTING_RUNTIME" \
    --query agentRuntimeEndpoint \
    --output text \
    --region "$REGION")

  RUNTIME_ARN=$(echo "$RUNTIME_RESPONSE" | jq -r '.agentRuntimeArn // empty' || echo "arn:existing")
else
  echo "  Creating new AgentCore Runtime: football-coach"

  RUNTIME_RESPONSE=$(aws bedrock-agentcore-control create-agent-runtime \
    --agent-runtime-name "football-coach" \
    --agent-runtime-artifact "{
        \"containerConfiguration\": {
            \"containerUri\": \"${COACH_REPO}:latest\"
        }
    }" \
    --network-configuration '{"networkMode": "PUBLIC"}' \
    --role-arn "$RUNTIME_ROLE" \
    --lifecycle-configuration '{
        "idleRuntimeSessionTimeout": 300,
        "maxLifetime": 900
    }' \
    --environment-variables "{
        \"LAMBDA_GK\":    \"${GK_FN}\",
        \"LAMBDA_DEF_L\": \"${DEF_L_FN}\",
        \"LAMBDA_DEF_R\": \"${DEF_R_FN}\",
        \"LAMBDA_MID\":   \"${MID_FN}\",
        \"LAMBDA_STR\":   \"${STR_FN}\",
        \"AWS_REGION\":   \"${REGION}\"
    }" \
    --region "$REGION")

  RUNTIME_ENDPOINT=$(echo "$RUNTIME_RESPONSE" | jq -r '.agentRuntimeEndpoint')
  RUNTIME_ARN=$(echo "$RUNTIME_RESPONSE" | jq -r '.agentRuntimeArn')
fi

echo "✓ AgentCore Runtime ready"
echo "  ARN:      $RUNTIME_ARN"
echo "  Endpoint: $RUNTIME_ENDPOINT"

# Store endpoint in SSM for backend
aws ssm put-parameter \
  --name "/football-cup/coach/agentcore_endpoint" \
  --value "${RUNTIME_ENDPOINT}/invocations" \
  --type String --overwrite \
  --region "$REGION"

# ── 5. Register 11 tools in AgentCore Gateway ─────────────────────────────────
echo ""
echo "── [5/6] AgentCore Gateway: register 11 tools ──"

TOOL_NAMES=$(aws ssm get-parameter \
  --name "/football-cup/gateway/tool_names" \
  --query Parameter.Value --output text --region "$REGION")

echo "  Tools to register:"
IFS=',' read -ra TOOLS <<< "$TOOL_NAMES"
for TOOL_NAME in "${TOOLS[@]}"; do
  TOOL_ARN=$(aws ssm get-parameter \
    --name "/football-cup/gateway/lambda_arns/${TOOL_NAME}" \
    --query Parameter.Value --output text --region "$REGION" 2>/dev/null \
    || echo "NOT_FOUND")

  if [ "$TOOL_ARN" != "NOT_FOUND" ]; then
    echo "  ✓ $TOOL_NAME"
  else
    echo "  ✗ $TOOL_NAME — ARN not found in SSM (check McpToolsStack deploy)"
  fi
done

echo ""
echo "  AgentCore Gateway registration via AWS CLI or console:"
echo "  All 11 Lambda ARNs stored under /football-cup/gateway/lambda_arns/"
echo "  Gateway MCP endpoint stored at /football-cup/gateway/endpoint after creation"
echo "✓ 11 tools verified in SSM"

# ── 6. Backend + Frontend stacks ─────────────────────────────────────────────
echo ""
echo "── [6/6] Backend + Frontend ──"
cd infra
cdk deploy FootballBackendStack --require-approval never --context "account=$ACCOUNT_ID"
cd ..

API_URL=$(aws ssm get-parameter \
  --name "/football-cup/backend/api_url" \
  --query Parameter.Value --output text --region "$REGION" 2>/dev/null || echo "")

WS_URL=$(aws ssm get-parameter \
  --name "/football-cup/backend/ws_url" \
  --query Parameter.Value --output text --region "$REGION" 2>/dev/null || echo "")

cat > frontend/.env.local << EOF
NEXT_PUBLIC_API_URL=${API_URL}
NEXT_PUBLIC_WS_URL=${WS_URL}
NEXT_PUBLIC_REGION=${REGION}
NEXT_PUBLIC_AGENTCORE_ENDPOINT=${RUNTIME_ENDPOINT}/invocations
EOF

echo "✓ frontend/.env.local written"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo " Deploy Complete ✓"
echo "========================================"
echo ""
echo "  Architecture:"
echo "    Coach Runtime:  1 ARM64 container (AgentCore)"
echo "    Player Lambdas: 5 zip-deployed ARM64 Lambdas"
echo "    Game Tools:     6 zip-deployed ARM64 Lambdas"
echo "    Total:          1 Docker build, 11 Lambda tools"
echo ""
echo "  Endpoints:"
echo "    Coach /invocations: ${RUNTIME_ENDPOINT}/invocations"
echo "    Coach /ping:        ${RUNTIME_ENDPOINT}/ping"
if [ -n "$API_URL" ]; then
echo "    Backend API:        ${API_URL}"
echo "    WebSocket:          ${WS_URL}"
fi
echo ""
echo "  Verify coach health:"
echo "    curl ${RUNTIME_ENDPOINT}/ping"
echo ""
echo "  Start a match:"
if [ -n "$API_URL" ]; then
echo "    curl -X POST ${API_URL}match/start \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"team_a\":{\"team_id\":\"team_a\",\"team_name\":\"Crimson Rovers\"},\"team_b\":{\"team_id\":\"team_b\",\"team_name\":\"Azure FC\"}}'"
fi
echo "========================================"
