"""
Backend Stack — FastAPI tick engine Lambda + HTTP API Gateway + WebSocket API Gateway.

Resources:
  - ECR repository for backend Docker image (ARM64)
  - Lambda: DockerImageFunction (ARM64, 1024 MB, 30s timeout)
  - HTTP API Gateway → FastAPI Lambda (REST routes)
  - WebSocket API Gateway → Lambda ($connect/$disconnect/$default)
  - IAM: invoke AgentCore endpoints, DynamoDB R/W, S3 R/W, SSM GetParameter
  - SSM parameters: API URL, WS URL (consumed by frontend build)
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_ssm as ssm,
)
from constructs import Construct


class BackendStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        storage_stack,
        agentcore_stack,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── ECR repository for backend image ─────────────────────────────
        backend_repo = ecr.Repository(
            self,
            "BackendRepo",
            repository_name="football-cup-backend",
            removal_policy=__import__("aws_cdk").RemovalPolicy.DESTROY,
            empty_on_delete=True,
            lifecycle_rules=[ecr.LifecycleRule(max_image_count=3)],
        )

        # Store backend ECR URI for deploy.sh
        ssm.StringParameter(
            self,
            "BackendRepoUri",
            parameter_name="/football-cup/backend/ecr_repo_uri",
            string_value=backend_repo.repository_uri,
        )

        # ── IAM Role for backend Lambda ───────────────────────────────────
        backend_role = iam.Role(
            self,
            "BackendLambdaRole",
            role_name="football-cup-backend-lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # DynamoDB: game state + squads + WS connections
        backend_role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBAll",
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:Query",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Scan",
                ],
                resources=[
                    storage_stack.game_state_table.table_arn,
                    f"{storage_stack.game_state_table.table_arn}/index/*",
                    storage_stack.squads_table.table_arn,
                    storage_stack.ws_connections_table.table_arn,
                    f"{storage_stack.ws_connections_table.table_arn}/index/*",
                ],
            )
        )

        # S3: event log read/write
        backend_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3EventLog",
                actions=["s3:GetObject", "s3:PutObject", "s3:HeadObject"],
                resources=[f"{storage_stack.events_bucket.bucket_arn}/*"],
            )
        )

        # SSM: read all /football-cup/* parameters (AgentCore endpoints)
        backend_role.add_to_policy(
            iam.PolicyStatement(
                sid="SSMRead",
                actions=["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/football-cup/*"
                ],
            )
        )

        # Execute AgentCore Runtime invocations (HTTPS via aiohttp — no special IAM needed)
        # But we need bedrock-agentcore:InvokeAgentRuntime for signed requests
        backend_role.add_to_policy(
            iam.PolicyStatement(
                sid="AgentCoreInvoke",
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=["*"],
            )
        )

        # API Gateway Management API: post to WebSocket connections
        backend_role.add_to_policy(
            iam.PolicyStatement(
                sid="ApiGatewayManagement",
                actions=["execute-api:ManageConnections"],
                resources=[f"arn:aws:execute-api:{self.region}:{self.account}:*/*/@connections/*"],
            )
        )

        # ── Lambda: FastAPI tick engine ───────────────────────────────────
        self.backend_fn = lambda_.DockerImageFunction(
            self,
            "BackendFn",
            function_name="football-cup-backend",
            code=lambda_.DockerImageCode.from_ecr(
                repository=backend_repo,
                tag_or_digest="latest",
            ),
            role=backend_role,
            architecture=lambda_.Architecture.ARM_64,
            memory_size=1024,
            timeout=Duration.seconds(30),
            reserved_concurrent_executions=10,
            environment={
                "TABLE_NAME": storage_stack.game_state_table.table_name,
                "SQUADS_TABLE_NAME": storage_stack.squads_table.table_name,
                "WS_TABLE_NAME": storage_stack.ws_connections_table.table_name,
                "BUCKET_NAME": storage_stack.events_bucket.bucket_name,
                "AWS_REGION": self.region,
                "ALLOWED_ORIGINS": "http://localhost:3000,https://*.amplifyapp.com",
            },
            description="Football Cup FastAPI tick engine + match manager",
        )

        # ── HTTP API Gateway ──────────────────────────────────────────────
        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name="football-cup-http-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_headers=["*"],
            ),
        )

        http_integration = integrations.HttpLambdaIntegration(
            "BackendIntegration", self.backend_fn
        )

        http_api.add_routes(
            path="/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=http_integration,
        )
        http_api.add_routes(
            path="/",
            methods=[apigwv2.HttpMethod.ANY],
            integration=http_integration,
        )

        # ── WebSocket API Gateway ─────────────────────────────────────────
        ws_integration = apigwv2.WebSocketLambdaIntegration(
            "WsIntegration", self.backend_fn
        )

        ws_api = apigwv2.WebSocketApi(
            self,
            "WsApi",
            api_name="football-cup-ws-api",
            connect_route_options=apigwv2.WebSocketRouteOptions(
                integration=ws_integration
            ),
            disconnect_route_options=apigwv2.WebSocketRouteOptions(
                integration=ws_integration
            ),
            default_route_options=apigwv2.WebSocketRouteOptions(
                integration=ws_integration
            ),
        )

        ws_stage = apigwv2.WebSocketStage(
            self,
            "WsStage",
            web_socket_api=ws_api,
            stage_name="prod",
            auto_deploy=True,
        )

        # Allow API GW to manage connections → backend Lambda needs the endpoint URL
        ws_endpoint = ws_stage.callback_url  # https://{id}.execute-api.{region}.amazonaws.com/prod

        # Inject WS endpoint URL into backend Lambda env after API creation
        self.backend_fn.add_environment("WS_ENDPOINT_URL", ws_endpoint)

        # ── SSM: store URLs for frontend build ────────────────────────────
        api_url = http_api.url or ""

        ssm.StringParameter(
            self,
            "ApiUrl",
            parameter_name="/football-cup/backend/api_url",
            string_value=api_url,
        )
        ssm.StringParameter(
            self,
            "WsUrl",
            parameter_name="/football-cup/backend/ws_url",
            string_value=ws_stage.url,
        )

        # ── Outputs ───────────────────────────────────────────────────────
        CfnOutput(self, "BackendApiUrl", value=api_url, export_name="football-cup-api-url")
        CfnOutput(self, "BackendWsUrl", value=ws_stage.url, export_name="football-cup-ws-url")
        CfnOutput(self, "BackendRepoUri", value=backend_repo.repository_uri)
        CfnOutput(self, "BackendFnArn", value=self.backend_fn.function_arn)
