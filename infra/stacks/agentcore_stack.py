"""
AgentCore Stack — infrastructure only, no Docker bundling.

Creates:
  ECR repos  : 1 coach + 5 player Lambdas
  IAM role   : AgentCore Runtime role (coach)
  IAM role   : Player Lambda execution role
  SSM params : ECR URIs + role ARNs
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

PLAYER_NAMES = [
    "goalkeeper",
    "defender-left",
    "defender-right",
    "midfielder",
    "striker",
]


class AgentCoreStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── ECR: coach container ──────────────────────────────────────────
        self.coach_repo = ecr.Repository(
            self, "CoachRepo",
            repository_name="football-cup-coach",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        # ── ECR: one repo per player Lambda ──────────────────────────────
        self.player_repos: dict[str, ecr.Repository] = {}
        for player in PLAYER_NAMES:
            repo = ecr.Repository(
                self, f"PlayerRepo{player.replace('-','').title()}",
                repository_name=f"football-player-{player}",
                removal_policy=RemovalPolicy.DESTROY,
                empty_on_delete=True,
            )
            self.player_repos[player] = repo
            ssm.StringParameter(
                self, f"PlayerEcr{player.replace('-','').title()}",
                parameter_name=f"/football-cup/ecr/players/{player}",
                string_value=repo.repository_uri,
            )

        # ── IAM: AgentCore Runtime role (coach container) ─────────────────
        self.runtime_role = iam.Role(
            self, "AgentRuntimeRole",
            role_name="football-coach-runtime-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("lambda.amazonaws.com"),
            ),
        )
        self.runtime_role.add_to_policy(iam.PolicyStatement(
            sid="BedrockInvoke",
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=[NOVA_MICRO_ARN],
        ))
        self.runtime_role.add_to_policy(iam.PolicyStatement(
            sid="SSMRead",
            actions=["ssm:GetParameter", "ssm:GetParameters"],
            resources=[f"arn:aws:ssm:us-east-1:{self.account}:parameter/football-cup/*"],
        ))
        self.runtime_role.add_to_policy(iam.PolicyStatement(
            sid="ECRPull",
            actions=[
                "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage",
                "ecr:BatchCheckLayerAvailability", "ecr:GetAuthorizationToken",
            ],
            resources=["*"],
        ))

        # ── IAM: player Lambda execution role ─────────────────────────────
        self.player_role = iam.Role(
            self, "PlayerLambdaRole",
            role_name="football-player-lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        self.player_role.add_to_policy(iam.PolicyStatement(
            sid="BedrockInvokePlayer",
            actions=["bedrock:InvokeModel"],
            resources=[NOVA_MICRO_ARN],
        ))

        # ── SSM: store key values for deploy script ───────────────────────
        ssm.StringParameter(
            self, "CoachRepoUri",
            parameter_name="/football-cup/coach/ecr_repo_uri",
            string_value=self.coach_repo.repository_uri,
        )
        ssm.StringParameter(
            self, "RuntimeRoleArn",
            parameter_name="/football-cup/coach/runtime_role_arn",
            string_value=self.runtime_role.role_arn,
        )
        ssm.StringParameter(
            self, "PlayerRoleArn",
            parameter_name="/football-cup/players/lambda_role_arn",
            string_value=self.player_role.role_arn,
        )

        # ── Outputs ───────────────────────────────────────────────────────
        CfnOutput(self, "CoachRepoUriOut", value=self.coach_repo.repository_uri)
        CfnOutput(self, "RuntimeRoleArnOut", value=self.runtime_role.role_arn)
        for player, repo in self.player_repos.items():
            CfnOutput(self, f"PlayerRepo{player.replace('-','').title()}Out",
                      value=repo.repository_uri)
