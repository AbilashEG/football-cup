#!/bin/bash
# =============================================================================
# Football Cup — CloudShell Deploy Script
#
# WHERE EACH STEP RUNS:
#   CloudShell  → CDK deploys, backend Docker build/push, AWS CLI calls
#   CodeBuild   → coach ARM64 image build only (triggered from here)
#
# HOW TO USE:
#   1. Open AWS CloudShell (us-east-1)
#   2. Upload this repo as a zip OR git clone it:
#        git clone https://github.com/YOUR_ORG/football-cup.git
#        cd football-cup
#   3. Run:
#        chmod +x deploy-cloudshell.sh
#        ./deploy-cloudshell.sh
#
# PREREQUISITES (all already in CloudShell):
#   - AWS CLI v2     ✓ pre-installed
#   - Docker         ✓ available in CloudShell
#   - Python 3.11    ✓ pre-installed
#   - Node.js 18+    ✓ pre-installed
#   - jq             ✓ pre-installed
# =============================================================================
set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
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
# PHASE 1: CDK — Storage + AgentCore + CodeBuild + MCP Tools + Gateway
# Runs entirely in CloudShell. No Docker needed.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 1 — CDK base stacks (CloudShell)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd infra
pip install -r requirements.txt --quiet --upgrade
npm install -g aws-cdk --quiet 2>/dev/null || true

# Bootstrap once (safe to re-run)
cdk bootstrap "aws://$ACCOUNT_ID/$REGION" --quiet 2>/dev/null || true

# Deploy in dependency order
cdk deploy \
  FootballStorageStack \
  FootballAgentCoreStack \
  FootballCodeBuildStack \
  FootballMcpToolsStack \
  FootballGatewayStack \
  --require-approval never \
  --context "account=$ACCOUNT_ID"

echo "✓ Base stacks deployed"
cd ..

# Read values we'll need throughout
COACH_REPO=$(aws ssm get-parameter \
  --name "/football-cup/coach/ecr_repo_uri" \
  --query Parameter.Value --output text --region "$REGION")

RUNTIME_ROLE=$(aws ssm get-parameter \
  --name "/football-cup/coach/runtime_role_arn" \
  --query Parameter.Value --output text --region "$REGION")

CB_PROJECT=$(aws ssm get-parameter \
  --name "/football-cup/codebuild/coach_project_name" \
  --query Parameter.Value --output text --region "$REGION")

CB_SOURCE_BUCKET=$(aws ssm get-parameter \
  --name "/football-cup/codebuild/source_bucket" \
  --query Parameter.Value --output text --region "$REGION")

echo "  Coach ECR:        $COACH_REPO"
echo "  Runtime Role:     $RUNTIME_ROLE"
echo "  CodeBuild project: $CB_PROJECT"
echo "  Source bucket:    $CB_SOURCE_BUCKET"

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: Upload repo zip to S3 → trigger CodeBuild → wait for completion
# CodeBuild builds the ARM64 coach image natively (no QEMU needed).
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 2 — Coach ARM64 image (CodeBuild)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "  Zipping repo for CodeBuild source..."
# Zip from repo root — buildspec and Dockerfile paths must be relative to root
zip -r /tmp/coach-source.zip . \
  --exclude "*.git*" \
  --exclude "node_modules/*" \
  --exclude "frontend/.next/*" \
  --exclude "__pycache__/*" \
  --exclude "*.pyc" \
  --exclude "cdk.out/*" \
  -q

echo "  Uploading source zip to S3..."
aws s3 cp /tmp/coach-source.zip \
  "s3://$CB_SOURCE_BUCKET/coach-source.zip" \
  --region "$REGION"
echo "  ✓ Source uploaded: s3://$CB_SOURCE_BUCKET/coach-source.zip"

echo "  Starting CodeBuild build..."
BUILD_ID=$(aws codebuild start-build \
  --project-name "$CB_PROJECT" \
  --region "$REGION" \
  --query "build.id" \
  --output text)

echo "  Build ID: $BUILD_ID"
echo "  Logs: https://$REGION.console.aws.amazon.com/cloudwatch/home?region=$REGION#logsV2:log-groups/log-group/%2Ffootball-cup%2Fcodebuild%2Fcoach"

# Poll until CodeBuild completes (check every 15s, timeout 15min)
echo "  Waiting for CodeBuild to complete (ARM64 build ~5-8 min)..."
ELAPSED=0
POLL_INTERVAL=15
MAX_WAIT=900

while [ $ELAPSED -lt $MAX_WAIT ]; do
  STATUS=$(aws codebuild batch-get-builds \
    --ids "$BUILD_ID" \
    --region "$REGION" \
    --query "builds[0].buildStatus" \
    --output text)

  PHASE=$(aws codebuild batch-get-builds \
    --ids "$BUILD_ID" \
    --region "$REGION" \
    --query "builds[0].currentPhase" \
    --output text)

  printf "  [%3ds] Status: %-12s Phase: %s\n" "$ELAPSED" "$STATUS" "$PHASE"

  if [ "$STATUS" = "SUCCEEDED" ]; then
    echo "  ✓ CodeBuild succeeded — coach ARM64 image pushed to ECR"
    break
  elif [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "STOPPED" ] || [ "$STATUS" = "TIMED_OUT" ]; then
    echo "  ✗ CodeBuild $STATUS — check logs:"
    echo "    https://$REGION.console.aws.amazon.com/cloudwatch/home?region=$REGION#logsV2:log-groups/log-group/%2Ffootball-cup%2Fcodebuild%2Fcoach"
    exit 1
  fi

  sleep $POLL_INTERVAL
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
  echo "  ✗ CodeBuild timed out after ${MAX_WAIT}s"
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: Build and push backend Docker image (CloudShell Docker)
# Backend is also ARM64. CloudShell Docker + buildx handles this with QEMU.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 3 — Backend Docker image (CloudShell)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Enable ARM64 emulation for buildx (one-time, safe to re-run)
docker run --privileged --rm tonistiigi/binfmt --install arm64 2>/dev/null || true

# Set up buildx builder
docker buildx inspect football-cup-builder 2>/dev/null \
  || docker buildx create --name football-cup-builder --use --driver docker-container
docker buildx use football-cup-builder

BACKEND_REPO=$(aws ssm get-parameter \
  --name "/football-cup/backend/ecr_repo_uri" \
  --query Parameter.Value --output text --region "$REGION" 2>/dev/null || echo "")

if [ -z "$BACKEND_REPO" ]; then
  echo "  ⚠ Backend ECR URI not in SSM yet — deploying BackendStack first..."
  cd infra
  cdk deploy FootballBackendStack \
    --require-approval never \
    --context "account=$ACCOUNT_ID"
  cd ..
  BACKEND_REPO=$(aws ssm get-parameter \
    --name "/football-cup/backend/ecr_repo_uri" \
    --query Parameter.Value --output text --region "$REGION")
fi

echo "  Backend ECR: $BACKEND_REPO"

ECR_REGISTRY=$(echo "$COACH_REPO" | cut -d'/' -f1)
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "  Building backend ARM64 image (CloudShell buildx + QEMU)..."
docker buildx build \
  --platform linux/arm64 \
  --file backend/Dockerfile \
  --tag "$BACKEND_REPO:latest" \
  --tag "$BACKEND_REPO:$TIMESTAMP" \
  --push \
  .

echo "  ✓ Backend image pushed: $BACKEND_REPO:latest"

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4: Create (or update) the AgentCore Runtime — football-coach
# 1 runtime only. Coach reads player Lambda names from env vars.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 4 — AgentCore Runtime (CloudShell)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

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
echo "    GK    = $GK_FN"
echo "    DEF_L = $DEF_L_FN"
echo "    DEF_R = $DEF_R_FN"
echo "    MID   = $MID_FN"
echo "    STR   = $STR_FN"

ENV_VARS="{
  \"LAMBDA_GK\":    \"${GK_FN}\",
  \"LAMBDA_DEF_L\": \"${DEF_L_FN}\",
  \"LAMBDA_DEF_R\": \"${DEF_R_FN}\",
  \"LAMBDA_MID\":   \"${MID_FN}\",
  \"LAMBDA_STR\":   \"${STR_FN}\",
  \"AWS_REGION\":   \"${REGION}\"
}"

# Check if runtime already exists
EXISTING_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
  --region "$REGION" \
  --query "agentRuntimes[?agentRuntimeName=='football-coach'].agentRuntimeId" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_ID" ] && [ "$EXISTING_ID" != "None" ] && [ "$EXISTING_ID" != "" ]; then
  echo "  Runtime already exists (ID: $EXISTING_ID) — updating image..."

  aws bedrock-agentcore-control update-agent-runtime \
    --agent-runtime-id "$EXISTING_ID" \
    --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${COACH_REPO}:latest\"}}" \
    --environment-variables "$ENV_VARS" \
    --region "$REGION" > /dev/null

  RUNTIME_ENDPOINT=$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$EXISTING_ID" \
    --query "agentRuntimeEndpoint" \
    --output text \
    --region "$REGION")

  echo "  ✓ Runtime updated"
else
  echo "  Creating new AgentCore Runtime: football-coach..."

  RESPONSE=$(aws bedrock-agentcore-control create-agent-runtime \
    --agent-runtime-name "football-coach" \
    --agent-runtime-artifact \
      "{\"containerConfiguration\":{\"containerUri\":\"${COACH_REPO}:latest\"}}" \
    --network-configuration '{"networkMode":"PUBLIC"}' \
    --role-arn "$RUNTIME_ROLE" \
    --lifecycle-configuration \
      '{"idleRuntimeSessionTimeout":300,"maxLifetime":900}' \
    --environment-variables "$ENV_VARS" \
    --region "$REGION")

  RUNTIME_ENDPOINT=$(echo "$RESPONSE" | jq -r '.agentRuntimeEndpoint')
  RUNTIME_ARN=$(echo "$RESPONSE" | jq -r '.agentRuntimeArn')

  echo "  ✓ Runtime created"
  echo "    ARN: $RUNTIME_ARN"
fi

echo "  Endpoint: $RUNTIME_ENDPOINT"

# Store for backend
aws ssm put-parameter \
  --name "/football-cup/coach/agentcore_endpoint" \
  --value "${RUNTIME_ENDPOINT}/invocations" \
  --type String --overwrite \
  --region "$REGION"
echo "  ✓ Endpoint stored in SSM"

# Verify health
echo "  Checking /ping..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  --max-time 10 "${RUNTIME_ENDPOINT}/ping" 2>/dev/null || echo "000")
if [ "$HTTP_STATUS" = "200" ]; then
  echo "  ✓ Coach runtime healthy (HTTP 200)"
else
  echo "  ⚠ Ping returned HTTP $HTTP_STATUS (runtime may still be starting)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5: Deploy Backend CDK stack + write frontend env
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 5 — Backend stack + Frontend env"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd infra
cdk deploy FootballBackendStack \
  --require-approval never \
  --context "account=$ACCOUNT_ID"
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

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 6: Deploy Frontend (Amplify)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PHASE 6 — Frontend (Amplify)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  NOTE: FootballFrontendStack requires a GitHub token in SSM."
echo "  Store it first:"
echo "    aws ssm put-parameter --name /football-cup/github_token \\"
echo "      --value 'ghp_YOUR_TOKEN' --type SecureString --region $REGION"
echo ""
echo "  Then run:"
echo "    cd infra && cdk deploy FootballFrontendStack --require-approval never"
echo ""
echo "  OR for local dev (no Amplify needed):"
echo "    cd frontend && npm install && npm run dev"

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo " Deploy Complete ✓"
echo "=============================================="
echo ""
echo " What ran where:"
echo "   CloudShell  → CDK stacks, backend Docker, AWS CLI"
echo "   CodeBuild   → coach ARM64 image (native ARM64 build)"
echo ""
echo " Endpoints:"
echo "   Coach /ping        : ${RUNTIME_ENDPOINT}/ping"
echo "   Coach /invocations : ${RUNTIME_ENDPOINT}/invocations"
if [ -n "$API_URL" ]; then
echo "   Backend API        : ${API_URL}"
echo "   WebSocket          : ${WS_URL}"
fi
echo ""
echo " Verify:"
echo "   curl ${RUNTIME_ENDPOINT}/ping"
if [ -n "$API_URL" ]; then
echo "   curl ${API_URL}health"
fi
echo ""
echo " Start a match:"
if [ -n "$API_URL" ]; then
echo "   curl -X POST ${API_URL}match/start \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"team_a\":{\"team_id\":\"team_a\",\"team_name\":\"Crimson Rovers\"},\"team_b\":{\"team_id\":\"team_b\",\"team_name\":\"Azure FC\"}}'"
fi
echo "=============================================="
