"""
AgentCore Stack — deploys ONE Runtime (football-coach).

NOT 5 runtimes. ONE runtime only.

What this stack creates:
  1. ONE ECR repository  — football-cup-coach (ARM64 image pushed by deploy.sh)
  2. IAM AgentRuntimeRole — assumed by bedrock.amazonaws.com + lambda.amazonaws.com
       - bedrock:InvokeModel on Nova Micro
       - lambda:InvokeFunction on football-player-* functions
       - ssm:GetParameter for /football-cup/* config
  3. SSM parameters storing ECR repo URI + role ARN (consumed by deploy.sh)

AgentCore Runtime instance is created by deploy.sh AFTER the image is pushed,
because CDK cannot create AgentCore Runtimes without a valid container URI.
deploy.sh calls aws bedrock-agentcore-control create-agent-runtime and stores
the resulting endpoint URI in SSM for the backend to load at cold start.
"""

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_ssm as ssm,
)
from constructs import Construct

NOVA_MICRO_ARN = "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0"


class AgentCoreStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── ONE ECR repository — coach container only ─────────────────────
        self.coach_repo = ecr.Repository(
            self,
            "CoachRepo",
            repository_name="football-cup-coach",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
            lifecycle_rules=[
                ecr.LifecycleRule(max_image_count=3, description="Keep last 3 images")
            ],
        )

        # ── IAM Role for AgentCore Runtime ────────────────────────────────
        # Container calls: Bedrock InvokeModel + Lambda InvokeFunction (player Lambdas)
        self.runtime_role = iam.Role(
            self,
            "AgentRuntimeRole",
            role_name="football-coach-runtime-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("lambda.amazonaws.com"),
            ),
            description="IAM role for the football-coach AgentCore Runtime container",
        )

        # Bedrock: invoke Nova Micro only
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvokeNovaMicro",
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[NOVA_MICRO_ARN],
            )
        )

        # Lambda: invoke all football-player-* functions (5 player Lambdas)
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokePlayerLambdas",
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:us-east-1:{self.account}:function:football-player-*"
                ],
            )
        )

        # SSM: read config parameters at container start
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="ReadSsmConfig",
                actions=["ssm:GetParameter", "ssm:GetParameters"],
                resources=[
                    f"arn:aws:ssm:us-east-1:{self.account}:parameter/football-cup/*"
                ],
            )
        )

        # ECR: pull own image
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="ECRPull",
                actions=[
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetAuthorizationToken",
                ],
                resources=["*"],
            )
        )

        # ── SSM: store values for deploy.sh ──────────────────────────────
        ssm.StringParameter(
            self,
            "CoachRepoUri",
            parameter_name="/football-cup/coach/ecr_repo_uri",
            string_value=self.coach_repo.repository_uri,
            description="ECR URI for football-coach ARM64 container",
        )

        ssm.StringParameter(
            self,
            "RuntimeRoleArn",
            parameter_name="/football-cup/coach/runtime_role_arn",
            string_value=self.runtime_role.role_arn,
            description="IAM role ARN for AgentCore Runtime",
        )

        # ── Outputs ───────────────────────────────────────────────────────
        CfnOutput(
            self,
            "CoachRepoUriOutput",
            value=self.coach_repo.repository_uri,
            export_name="football-cup-coach-ecr-uri",
        )
        CfnOutput(
            self,
            "RuntimeRoleArnOutput",
            value=self.runtime_role.role_arn,
            export_name="football-cup-runtime-role-arn",
        )
