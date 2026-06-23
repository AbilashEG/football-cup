#!/bin/bash
# =============================================================================
# build_lambdas.sh
# Pre-build script — run ONCE in CloudShell before CDK deploy.
# Installs Python deps into each Lambda directory using pip (no Docker).
# CDK then just zips the directory as-is — no bundling needed.
# =============================================================================
set -euo pipefail

echo "=== Pre-building Lambda packages (pip, no Docker) ==="
cd "$(dirname "$0")"   # repo root

DEPS="strands-agents strands-agents-tools boto3 pydantic awscrt botocore requests"

# ── 1. Install deps once into a shared temp dir ───────────────────────────────
echo "Installing shared deps (once)..."
rm -rf /tmp/lambda-deps
mkdir -p /tmp/lambda-deps
pip install $DEPS -t /tmp/lambda-deps/ --quiet
echo "✓ Deps installed into /tmp/lambda-deps"

# ── 2. Build each player Lambda ───────────────────────────────────────────────
for PLAYER in goalkeeper defender_left defender_right midfielder striker; do
    echo "Building players/$PLAYER..."
    # Copy deps
    cp -r /tmp/lambda-deps/. players/$PLAYER/
    # Copy shared schemas (command_schema.py, game_state.py)
    mkdir -p players/$PLAYER/shared
    cp agents/shared/*.py players/$PLAYER/shared/
    echo "  ✓ players/$PLAYER ready"
done

# ── 3. Build each game tool Lambda ───────────────────────────────────────────
TOOL_DEPS="boto3 pydantic requests"
rm -rf /tmp/tool-deps
mkdir -p /tmp/tool-deps
pip install $TOOL_DEPS -t /tmp/tool-deps/ --quiet

for TOOL in get_game_state get_ball_trajectory get_nearest_opponent evaluate_shot_angle get_pass_success_rate log_agent_decision; do
    if [ -d "mcp_tools/$TOOL" ]; then
        echo "Building mcp_tools/$TOOL..."
        cp -r /tmp/tool-deps/. mcp_tools/$TOOL/
        echo "  ✓ mcp_tools/$TOOL ready"
    fi
done

echo ""
echo "=== All Lambda packages built ==="
echo "Now run: cd infra && cdk deploy FootballStorageStack --require-approval never"
