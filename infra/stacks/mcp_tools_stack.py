"""
MCP Tools Stack — Lambda functions using ECR container images.

NO Docker bundling in CDK.
Images are built by CodeBuild and pushed to ECR.
CDK creates Lambda functions pointing to ECR repos.

Deploy order:
  1. FootballAgentCoreStack  (creates ECR repos + IAM roles)
  2. CodeBuild trigger       (pushes images to ECR)
  3. FootballMcpToolsStack   (creates Lambda functions from ECR images)
"""

import aws_cdk as cdk
from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_ssm as ssm,
)
from constructs import Construct


PLAYER_TOOLS = [
    # (player_name,    ecr_repo_name,                 function_name,                   ssm_player_key)
    ("goalkeeper",     "football-player-goalkeeper",  "football-player-goalkeeper",    "goalkeeper"),
    ("defender_left",  "football-player-defender-left", "football-player-defender-left", "defender-left"),
    ("defender_right", "football-player-defender-right", "football-player-defender-right", "defender-right"),
    ("midfielder",     "football-player-midfielder",  "football-player-midfielder",    "midfielder"),
    ("striker",        "football-player-striker",     "football-player-striker",       "striker"),
]

GAME_TOOLS = [
    ("get_game_state",        "football-tool-get-game-state"),
    ("get_ball_trajectory",   "football-tool-get-ball-trajectory"),
    ("get_nearest_opponent",  "football-tool-get-nearest-opponent"),
    ("evaluate_shot_angle",   "football-tool-evaluate-shot-angle"),
    ("get_pass_success_rate", "football-tool-get-pass-success-rate"),
    ("log_agent_decision",    "football-tool-log-agent-decision"),
]


def _pascal(s: str) -> str:
    return "".join(w.capitalize() for w in s.replace("-", "_").split("_"))


class McpToolsStack(Stack):
    def __init__(self, scope, id: str, storage_stack, agentcore_stack, **kwargs):
        super().__init__(scope, id, **kwargs)

        self.lambda_arns: dict[str, str] = {}

        # ── 5 Player Lambda functions (container images from ECR) ─────────
        for name, ecr_name, function_name, ssm_key in PLAYER_TOOLS:
            # Reference ECR repo created by AgentCoreStack
            repo = ecr.Repository.from_repository_name(
                self, f"PlayerEcrRef{_pascal(name)}",
                repository_name=ecr_name,
            )

            fn = lambda_.DockerImageFunction(
                self, f"Player{_pascal(name)}",
                function_name=function_name,
                code=lambda_.DockerImageCode.from_ecr(
                    repository=repo,
                    tag_or_digest="latest",
                ),
                architecture=lambda_.Architecture.ARM_64,
                role=agentcore_stack.player_role,
                timeout=Duration.seconds(30),
                memory_size=512,
                environment={
                    "PYTHONPATH": "/var/task:/var/task/shared",
                    "AWS_REGION_NAME": "us-east-1",
                },
                description=f"Football player agent: {name}",
            )

            self.lambda_arns[function_name] = fn.function_arn

            # SSM: function name (coach reads this)
            ssm.StringParameter(
                self, f"PlayerFnName{_pascal(name)}",
                parameter_name=f"/football-cup/players/{name.replace('_','-')}/function_name",
                string_value=function_name,
            )
            # SSM: ARN for Gateway registration
            ssm.StringParameter(
                self, f"PlayerFnArn{_pascal(name)}",
                parameter_name=f"/football-cup/gateway/lambda_arns/{function_name}",
                string_value=fn.function_arn,
            )

            CfnOutput(self, f"Player{_pascal(name)}Arn", value=fn.function_arn)

        # ── 6 Game tool Lambda functions (zip deploy — no Docker needed) ──
        game_role = iam.Role(
            self, "GameToolRole",
            role_name="football-game-tool-lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        game_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"],
            resources=[
                storage_stack.game_state_table.table_arn,
                f"{storage_stack.game_state_table.table_arn}/index/*",
            ],
        ))
        game_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject"],
            resources=[f"{storage_stack.events_bucket.bucket_arn}/*"],
        ))

        for name, function_name in GAME_TOOLS:
            source_dir = f"../mcp_tools/{name}"
            fn = lambda_.Function(
                self, f"Tool{_pascal(name)}",
                function_name=function_name,
                runtime=lambda_.Runtime.PYTHON_3_11,
                architecture=lambda_.Architecture.ARM_64,
                handler="handler.handler",
                code=lambda_.Code.from_asset(source_dir),
                role=game_role,
                timeout=Duration.seconds(10),
                memory_size=256,
                environment={
                    "TABLE_NAME": storage_stack.game_state_table.table_name,
                    "BUCKET_NAME": storage_stack.events_bucket.bucket_name,
                },
            )
            self.lambda_arns[function_name] = fn.function_arn
            ssm.StringParameter(
                self, f"GameToolArn{_pascal(name)}",
                parameter_name=f"/football-cup/gateway/lambda_arns/{function_name}",
                string_value=fn.function_arn,
            )
