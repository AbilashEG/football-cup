"""
MCP Tools Stack — 11 Lambda functions total:

  5 player agents  (goalkeeper, defender_left, defender_right, midfielder, striker)
  6 game tools     (get_game_state, get_ball_trajectory, get_nearest_opponent,
                    evaluate_shot_angle, get_pass_success_rate, log_agent_decision)

All ARM64. Lambda ARNs stored in SSM for GatewayStack and deploy.sh.

Player Lambdas:
  - Bundled with strands-agents, boto3, pydantic + shared/ schema files
  - 5s timeout (1s used internally; 4s buffer)
  - 256 MB memory
  - PYTHONPATH includes /var/task/shared

Game tool Lambdas:
  - Unchanged from original McpToolsStack
  - 10s timeout, 256 MB
  - Access to DynamoDB + S3
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_ssm as ssm,
)
from constructs import Construct

PLAYER_TOOLS = [
    # (short_name,      function_name,                    source_dir)
    ("goalkeeper",      "football-player-goalkeeper",     "../players/goalkeeper"),
    ("defender_left",   "football-player-defender-left",  "../players/defender_left"),
    ("defender_right",  "football-player-defender-right", "../players/defender_right"),
    ("midfielder",      "football-player-midfielder",     "../players/midfielder"),
    ("striker",         "football-player-striker",        "../players/striker"),
]

GAME_TOOLS = [
    # (short_name,            function_name,                          source_dir)
    ("get_game_state",        "football-tool-get-game-state",        "../mcp_tools/get_game_state"),
    ("get_ball_trajectory",   "football-tool-get-ball-trajectory",   "../mcp_tools/get_ball_trajectory"),
    ("get_nearest_opponent",  "football-tool-get-nearest-opponent",  "../mcp_tools/get_nearest_opponent"),
    ("evaluate_shot_angle",   "football-tool-evaluate-shot-angle",   "../mcp_tools/evaluate_shot_angle"),
    ("get_pass_success_rate", "football-tool-get-pass-success-rate", "../mcp_tools/get_pass_success_rate"),
    ("log_agent_decision",    "football-tool-log-agent-decision",    "../mcp_tools/log_agent_decision"),
]


def _pascal(snake: str) -> str:
    """Convert snake_case → PascalCase for CDK logical IDs."""
    return "".join(word.capitalize() for word in snake.split("_"))


class McpToolsStack(Stack):
    def __init__(self, scope, id: str, storage_stack, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Public dict: function_name → ARN  (consumed by GatewayStack)
        self.lambda_arns: dict[str, str] = {}

        # ── IAM: player Lambdas ───────────────────────────────────────────
        player_policy = iam.ManagedPolicy(
            self,
            "PlayerLambdaPolicy",
            managed_policy_name="football-player-lambda-policy",
            statements=[
                iam.PolicyStatement(
                    sid="BedrockInvoke",
                    actions=["bedrock:InvokeModel"],
                    resources=[
                        "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0"
                    ],
                ),
                iam.PolicyStatement(
                    sid="DynamoDBPlayerAccess",
                    actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
                    resources=[storage_stack.game_state_table.table_arn],
                ),
            ],
        )

        player_role = iam.Role(
            self,
            "PlayerLambdaRole",
            role_name="football-player-lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                player_policy,
            ],
        )

        # ── Player Lambdas (5 × ARM64, zip deploy) ────────────────────────
        for name, function_name, source_dir in PLAYER_TOOLS:
            fn = lambda_.Function(
                self,
                f"Player{_pascal(name)}",
                function_name=function_name,
                runtime=lambda_.Runtime.PYTHON_3_11,
                architecture=lambda_.Architecture.ARM_64,   # ARM64 — no Docker needed
                handler="handler.handler",
                code=lambda_.Code.from_asset(
                    source_dir,
                    bundling=lambda_.BundlingOptions(
                        image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                        platform="linux/arm64",
                        command=[
                            "bash", "-c",
                            # Install deps into /asset-output
                            "pip install strands-agents boto3 pydantic -t /asset-output --quiet"
                            # Copy handler
                            " && cp -r . /asset-output"
                            # Bundle shared schemas alongside handler
                            " && mkdir -p /asset-output/shared"
                            " && cp /asset-input/../../../agents/shared/*.py /asset-output/shared/ 2>/dev/null"
                            " || cp /asset-input/../../agents/shared/*.py /asset-output/shared/",
                        ],
                    ),
                ),
                role=player_role,
                timeout=Duration.seconds(5),    # 5s total; 1s used by Strands + Bedrock
                memory_size=256,
                environment={
                    "PYTHONPATH": "/var/task:/var/task/shared",
                    "AWS_REGION_NAME": "us-east-1",
                },
                description=f"Football player agent: {name} (Strands + Nova Micro)",
            )

            self.lambda_arns[function_name] = fn.function_arn

            # SSM: store function name for coach env vars
            ssm.StringParameter(
                self,
                f"PlayerFnName{_pascal(name)}",
                parameter_name=f"/football-cup/players/{name}/function_name",
                string_value=function_name,
            )

            # SSM: store ARN for GatewayStack
            ssm.StringParameter(
                self,
                f"PlayerFnArn{_pascal(name)}",
                parameter_name=f"/football-cup/gateway/lambda_arns/{function_name}",
                string_value=fn.function_arn,
            )

            CfnOutput(self, f"Player{_pascal(name)}Arn", value=fn.function_arn)

        # ── IAM: game tool Lambdas ────────────────────────────────────────
        game_role = iam.Role(
            self,
            "GameToolRole",
            role_name="football-game-tool-lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        game_role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBGameTools",
                actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"],
                resources=[
                    storage_stack.game_state_table.table_arn,
                    f"{storage_stack.game_state_table.table_arn}/index/*",
                ],
            )
        )

        game_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3GameTools",
                actions=["s3:GetObject", "s3:PutObject", "s3:HeadObject"],
                resources=[f"{storage_stack.events_bucket.bucket_arn}/*"],
            )
        )

        # ── Game tool Lambdas (6 × ARM64, zip deploy) ─────────────────────
        for name, function_name, source_dir in GAME_TOOLS:
            fn = lambda_.Function(
                self,
                f"Tool{_pascal(name)}",
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
                description=f"Football MCP game tool: {name}",
            )

            self.lambda_arns[function_name] = fn.function_arn

            # SSM: store ARN for GatewayStack
            ssm.StringParameter(
                self,
                f"GameToolArn{_pascal(name)}",
                parameter_name=f"/football-cup/gateway/lambda_arns/{function_name}",
                string_value=fn.function_arn,
            )

            CfnOutput(self, f"Tool{_pascal(name)}Arn", value=fn.function_arn)
