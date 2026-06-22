#!/usr/bin/env python3
"""
CDK App entry point — Football Cup infrastructure.

Architecture:
  1 AgentCore Runtime  — coach container (ARM64, built by CodeBuild)
  11 Lambda tools      — 5 player agents + 6 game tools (zip deploy, no Docker)
  1 AgentCore Gateway  — MCP endpoint (created by deploy-cloudshell.sh)
  1 Backend Lambda     — FastAPI tick engine (ARM64, built by CloudShell Docker)
  1 Frontend           — Next.js on Amplify

Stack deploy order:
  1.  FootballStorageStack    — DynamoDB + S3
  2.  FootballAgentCoreStack  — 1 ECR repo (coach) + IAM role
  3.  FootballCodeBuildStack  — CodeBuild project (ARM64 coach image build)
  4.  FootballMcpToolsStack   — 11 Lambda functions
  5.  FootballGatewayStack    — SSM manifest for Gateway
  6.  FootballBackendStack    — FastAPI Lambda + HTTP + WebSocket API
  7.  FootballFrontendStack   — Next.js on Amplify

Run all:   cdk deploy --all --require-approval never
Run one:   cdk deploy FootballStorageStack
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
    region="us-east-1",   # Nova Micro + AgentCore Runtime available here
)

# ── 1. Storage ────────────────────────────────────────────────────────────────
storage = StorageStack(
    app, "FootballStorageStack", env=env,
    description="Football Cup — DynamoDB tables + S3 events bucket",
)

# ── 2. AgentCore (1 ECR repo + IAM) ──────────────────────────────────────────
agentcore = AgentCoreStack(
    app, "FootballAgentCoreStack", env=env,
    description="Football Cup — coach ECR repo + AgentCore Runtime IAM role",
)

# ── 3. CodeBuild (ARM64 coach image — triggered by deploy-cloudshell.sh) ─────
codebuild_stack = CodeBuildStack(
    app, "FootballCodeBuildStack",
    agentcore_stack=agentcore,
    env=env,
    description="Football Cup — CodeBuild ARM64 project for coach container only",
)
codebuild_stack.add_dependency(agentcore)

# ── 4. MCP Tools (11 Lambda functions — 5 players + 6 game tools) ────────────
mcp_tools = McpToolsStack(
    app, "FootballMcpToolsStack",
    storage_stack=storage,
    env=env,
    description="Football Cup — 11 Lambda tools: 5 player agents + 6 game tools (ARM64 zip)",
)
mcp_tools.add_dependency(storage)

# ── 5. Gateway (SSM manifest + endpoint placeholder) ─────────────────────────
gateway = GatewayStack(
    app, "FootballGatewayStack",
    mcp_tools_stack=mcp_tools,
    env=env,
    description="Football Cup — AgentCore Gateway SSM config (Gateway created by deploy script)",
)
gateway.add_dependency(mcp_tools)

# ── 6. Backend (FastAPI Lambda — backend Docker built in CloudShell) ──────────
backend = BackendStack(
    app, "FootballBackendStack",
    storage_stack=storage,
    agentcore_stack=agentcore,
    env=env,
    description="Football Cup — FastAPI tick engine Lambda + HTTP + WebSocket API",
)
backend.add_dependency(storage)
backend.add_dependency(agentcore)

# ── 7. Frontend (Next.js on Amplify) ─────────────────────────────────────────
frontend = FrontendStack(
    app, "FootballFrontendStack",
    backend_stack=backend,
    env=env,
    description="Football Cup — Next.js 14 on AWS Amplify",
)
frontend.add_dependency(backend)

app.synth()
