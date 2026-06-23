#!/usr/bin/env python3
"""
CDK App — Football Cup

DEPLOY ORDER (2 phases):

PHASE 1 — Infrastructure only (no Lambda code needed):
  cdk deploy FootballStorageStack
  cdk deploy FootballAgentCoreStack     ← creates ECR repos + IAM roles
  cdk deploy FootballCodeBuildStack     ← creates CodeBuild project

  Then trigger CodeBuild → waits for SUCCEEDED
  CodeBuild pushes: coach image + 5 player images → ECR

PHASE 2 — After images exist in ECR:
  cdk deploy FootballMcpToolsStack      ← creates Lambda functions from ECR images
  cdk deploy FootballGatewayStack       ← SSM manifest
  cdk deploy FootballBackendStack       ← backend Lambda + API Gateway
  cdk deploy FootballFrontendStack      ← Amplify (optional)
"""

import aws_cdk as cdk

from stacks.agentcore_stack import AgentCoreStack
from stacks.backend_stack import BackendStack
from stacks.codebuild_stack import CodeBuildStack
from stacks.frontend_stack import FrontendStack
from stacks.gateway_stack import GatewayStack
from stacks.mcp_tools_stack import McpToolsStack
from stacks.storage_stack import StorageStack

app = cdk.App()
env = cdk.Environment(
    account=app.node.try_get_context("account") or None,
    region="us-east-1",
)

# ── PHASE 1 stacks ────────────────────────────────────────────────────────────
storage = StorageStack(app, "FootballStorageStack", env=env,
    description="DynamoDB tables + S3 events bucket")

agentcore = AgentCoreStack(app, "FootballAgentCoreStack", env=env,
    description="ECR repos (coach + 5 players) + IAM roles")

codebuild_stack = CodeBuildStack(app, "FootballCodeBuildStack",
    agentcore_stack=agentcore, env=env,
    description="CodeBuild project — builds coach + 5 player ARM64 images")
codebuild_stack.add_dependency(agentcore)

# ── PHASE 2 stacks (run after CodeBuild pushes images) ───────────────────────
mcp_tools = McpToolsStack(app, "FootballMcpToolsStack",
    storage_stack=storage, agentcore_stack=agentcore, env=env,
    description="11 Lambda tools: 5 player (ECR) + 6 game tools (zip)")
mcp_tools.add_dependency(storage)
mcp_tools.add_dependency(agentcore)

gateway = GatewayStack(app, "FootballGatewayStack",
    mcp_tools_stack=mcp_tools, env=env,
    description="AgentCore Gateway SSM config")
gateway.add_dependency(mcp_tools)

backend = BackendStack(app, "FootballBackendStack",
    storage_stack=storage, agentcore_stack=agentcore, env=env,
    description="FastAPI backend Lambda + HTTP API + WebSocket API")
backend.add_dependency(storage)
backend.add_dependency(agentcore)

frontend = FrontendStack(app, "FootballFrontendStack",
    backend_stack=backend, env=env,
    description="Next.js on Amplify")
frontend.add_dependency(backend)

app.synth()
