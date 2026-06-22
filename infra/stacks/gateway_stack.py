"""
Gateway Stack — AgentCore Gateway.

Registers all 11 Lambda tools as one MCP server endpoint that the
coach agent connects to for player tool calls.

CDK does not yet have L2 constructs for AgentCore Gateway creation,
so this stack's job is:
  1. Store all 11 Lambda ARNs in SSM (already done by McpToolsStack,
     but consolidated here for clarity)
  2. Expose a CfnOutput with tool count so deploy.sh can verify
  3. deploy.sh creates the actual Gateway via AWS CLI post-CDK-deploy

Tool naming convention in Gateway:
  player_gk          → football-player-goalkeeper
  player_def_l       → football-player-defender-left
  player_def_r       → football-player-defender-right
  player_mid         → football-player-midfielder
  player_str         → football-player-striker
  get_game_state     → football-tool-get-game-state
  get_ball_trajectory→ football-tool-get-ball-trajectory
  get_nearest_opponent → football-tool-get-nearest-opponent
  evaluate_shot_angle  → football-tool-evaluate-shot-angle
  get_pass_success_rate→ football-tool-get-pass-success-rate
  log_agent_decision   → football-tool-log-agent-decision
"""

from aws_cdk import CfnOutput, Stack, aws_ssm as ssm
from constructs import Construct

# All 11 tool names that will be registered in AgentCore Gateway
ALL_GATEWAY_TOOLS = [
    # Player agents (5)
    "football-player-goalkeeper",
    "football-player-defender-left",
    "football-player-defender-right",
    "football-player-midfielder",
    "football-player-striker",
    # Game tools (6)
    "football-tool-get-game-state",
    "football-tool-get-ball-trajectory",
    "football-tool-get-nearest-opponent",
    "football-tool-evaluate-shot-angle",
    "football-tool-get-pass-success-rate",
    "football-tool-log-agent-decision",
]


class GatewayStack(Stack):
    def __init__(self, scope, id: str, mcp_tools_stack, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Verify all expected tools have ARNs from McpToolsStack
        missing = [t for t in ALL_GATEWAY_TOOLS if t not in mcp_tools_stack.lambda_arns]
        if missing:
            raise ValueError(
                f"GatewayStack: missing Lambda ARNs from McpToolsStack: {missing}"
            )

        # SSM: store Gateway tool manifest (used by deploy.sh to register tools)
        # Individual ARNs already stored by McpToolsStack under /football-cup/gateway/lambda_arns/<name>
        # Store the tool list as a comma-separated manifest for easy shell iteration
        ssm.StringParameter(
            self,
            "GatewayToolManifest",
            parameter_name="/football-cup/gateway/tool_names",
            string_value=",".join(ALL_GATEWAY_TOOLS),
            description="Comma-separated list of all 11 Lambda tool names for Gateway registration",
        )

        # SSM: placeholder for Gateway endpoint (written by deploy.sh after creation)
        ssm.StringParameter(
            self,
            "GatewayEndpointPlaceholder",
            parameter_name="/football-cup/gateway/endpoint",
            string_value="PENDING_DEPLOY",
            description="AgentCore Gateway MCP endpoint URL — set by deploy.sh",
        )

        # ── Outputs ───────────────────────────────────────────────────────
        CfnOutput(
            self,
            "GatewayToolCount",
            value=str(len(ALL_GATEWAY_TOOLS)),
            description="Number of Lambda tools to register in AgentCore Gateway",
        )

        CfnOutput(
            self,
            "GatewayToolManifestParam",
            value="/football-cup/gateway/tool_names",
            description="SSM parameter name listing all Gateway tools",
        )
