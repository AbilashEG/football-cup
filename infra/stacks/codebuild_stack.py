"""
CodeBuild Stack — builds ALL Docker images:
  1. coach/          → python:3.12-slim  → ECR football-cup-coach
  2. players/ (×5)   → lambda/python:3.12 → ECR football-player-{name}

ARM64 native build (LinuxArmBuildImage) — no QEMU needed.
Source: curl download from GitHub (NOT git clone).
GitHub: AbilashEG/football-cup (ONE E)
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_codebuild as codebuild,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
    aws_ssm as ssm,
)
from constructs import Construct

PLAYERS = [
    "goalkeeper",
    "defender-left",
    "defender-right",
    "midfielder",
    "striker",
]


class CodeBuildStack(Stack):
    def __init__(self, scope: Construct, id: str, agentcore_stack, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── S3 source bucket (satisfies CDK source requirement) ───────────
        source_bucket = s3.Bucket(
            self, "CoachSourceBucket",
            bucket_name=f"football-cup-codebuild-src-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ── IAM role for CodeBuild ────────────────────────────────────────
        cb_role = iam.Role(
            self, "CodeBuildRole",
            role_name="football-cup-codebuild-role",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
        )
        cb_role.add_to_policy(iam.PolicyStatement(
            sid="ECRAll",
            actions=[
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "ecr:InitiateLayerUpload",
                "ecr:UploadLayerPart",
                "ecr:CompleteLayerUpload",
                "ecr:PutImage",
            ],
            resources=["*"],
        ))
        cb_role.add_to_policy(iam.PolicyStatement(
            sid="SSMWrite",
            actions=["ssm:PutParameter", "ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/football-cup/*"],
        ))
        cb_role.add_to_policy(iam.PolicyStatement(
            sid="S3Read",
            actions=["s3:GetObject", "s3:GetObjectVersion", "s3:ListBucket"],
            resources=[source_bucket.bucket_arn, f"{source_bucket.bucket_arn}/*"],
        ))
        cb_role.add_to_policy(iam.PolicyStatement(
            sid="CWLogs",
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=["*"],
        ))
        cb_role.add_to_policy(iam.PolicyStatement(
            sid="STS",
            actions=["sts:GetCallerIdentity"],
            resources=["*"],
        ))

        # ── CloudWatch log group ──────────────────────────────────────────
        log_group = logs.LogGroup(
            self, "BuildLogs",
            log_group_name="/aws/codebuild/football-cup-coach-build",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # ── Build env vars: one per ECR repo ─────────────────────────────
        env_vars = {
            "COACH_REPO_URI": codebuild.BuildEnvironmentVariable(
                value=agentcore_stack.coach_repo.repository_uri,
            ),
            "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(
                value=self.region,
            ),
        }
        for player in PLAYERS:
            key = f"PLAYER_{player.upper().replace('-','_')}_REPO"
            env_vars[key] = codebuild.BuildEnvironmentVariable(
                value=agentcore_stack.player_repos[player].repository_uri,
            )

        # ── Inline buildspec ──────────────────────────────────────────────
        # Downloads repo via curl (NOT git clone — auth fails)
        # GitHub: AbilashEG (ONE E)
        build_commands = [
            "echo 'Downloading source from GitHub...'",
            "curl -L -o source.zip https://github.com/AbilashEG/football-cup/archive/refs/heads/main.zip",
            "ZIP_SIZE=$(wc -c < source.zip)",
            "echo \"ZIP size = ${ZIP_SIZE} bytes\"",
            "if [ \"$ZIP_SIZE\" -lt 1000 ]; then echo 'ERROR: ZIP too small'; exit 1; fi",
            "unzip -q source.zip",
            "cd football-cup-main",
            # ECR login
            "ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --no-cli-pager)",
            "ECR_REGISTRY=${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com",
            "IMAGE_TAG=$(date +%Y%m%d-%H%M%S)",
            "aws ecr get-login-password --region ${AWS_DEFAULT_REGION} --no-cli-pager | docker login --username AWS --password-stdin ${ECR_REGISTRY}",
            # Build coach image
            "echo '=== Building coach image ==='",
            "docker build --file coach/Dockerfile --tag ${COACH_REPO_URI}:latest --tag ${COACH_REPO_URI}:${IMAGE_TAG} .",
            "docker push ${COACH_REPO_URI}:latest",
            "docker push ${COACH_REPO_URI}:${IMAGE_TAG}",
            "echo 'Coach pushed'",
        ]

        # Build each player image
        for player in PLAYERS:
            key = f"PLAYER_{player.upper().replace('-','_')}_REPO"
            build_commands += [
                f"echo '=== Building player: {player} ==='",
                f"docker build --build-arg PLAYER={player} --file players/Dockerfile --tag ${{{key}}}:latest --tag ${{{key}}}:${{IMAGE_TAG}} .",
                f"docker push ${{{key}}}:latest",
                f"docker push ${{{key}}}:${{IMAGE_TAG}}",
                f"echo '{player} pushed'",
            ]

        build_commands.append(
            "aws ssm put-parameter --name /football-cup/coach/last_build_tag --value ${IMAGE_TAG} --type String --overwrite --region ${AWS_DEFAULT_REGION} --no-cli-pager"
        )
        build_commands.append("echo '=== ALL IMAGES BUILT ==='")

        inline_buildspec = codebuild.BuildSpec.from_object({
            "version": "0.2",
            "phases": {
                "pre_build": {
                    "commands": [
                        "curl -L -o source.zip https://github.com/AbilashEG/football-cup/archive/refs/heads/main.zip",
                        "ZIP_SIZE=$(wc -c < source.zip)",
                        "echo \"ZIP size = ${ZIP_SIZE} bytes\"",
                        "if [ \"$ZIP_SIZE\" -lt 1000 ]; then echo 'ERROR: ZIP too small — check GitHub username AbilashEG'; exit 1; fi",
                        "unzip -q source.zip",
                        "ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --no-cli-pager)",
                        "ECR_REGISTRY=${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com",
                        "IMAGE_TAG=$(date +%Y%m%d-%H%M%S)",
                        "echo \"Registry=${ECR_REGISTRY} Tag=${IMAGE_TAG}\"",
                        "aws ecr get-login-password --region ${AWS_DEFAULT_REGION} --no-cli-pager | docker login --username AWS --password-stdin ${ECR_REGISTRY}",
                    ]
                },
                "build": {
                    "commands": [
                        "cd football-cup-main",
                        # Coach
                        "echo '--- Building coach ---'",
                        "docker build --file coach/Dockerfile --tag ${COACH_REPO_URI}:latest --tag ${COACH_REPO_URI}:${IMAGE_TAG} .",
                        # Players
                        *[
                            cmd
                            for player in PLAYERS
                            for cmd in [
                                f"echo '--- Building player: {player} ---'",
                                f"docker build --build-arg PLAYER={player} --file players/Dockerfile "
                                f"--tag ${{PLAYER_{player.upper().replace('-','_')}_REPO}}:latest "
                                f"--tag ${{PLAYER_{player.upper().replace('-','_')}_REPO}}:${{IMAGE_TAG}} .",
                            ]
                        ],
                    ]
                },
                "post_build": {
                    "commands": [
                        "cd football-cup-main",
                        "docker push ${COACH_REPO_URI}:latest",
                        *[
                            f"docker push ${{PLAYER_{p.upper().replace('-','_')}_REPO}}:latest"
                            for p in PLAYERS
                        ],
                        "aws ssm put-parameter --name /football-cup/coach/last_build_tag --value ${IMAGE_TAG} --type String --overwrite --region ${AWS_DEFAULT_REGION} --no-cli-pager",
                        "echo '=== ALL IMAGES PUSHED TO ECR ==='",
                    ]
                },
            },
        })

        # ── CodeBuild project ─────────────────────────────────────────────
        self.coach_build_project = codebuild.Project(
            self, "AllImagesBuildProject",
            project_name="football-cup-coach-build",
            description="Builds coach + 5 player Lambda images (ARM64 native)",
            source=codebuild.Source.s3(bucket=source_bucket, path=""),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0,
                compute_type=codebuild.ComputeType.SMALL,
                privileged=True,
            ),
            build_spec=inline_buildspec,
            environment_variables=env_vars,
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(
                    log_group=log_group, enabled=True,
                )
            ),
            timeout=Duration.minutes(30),
            role=cb_role,
        )

        # ── SSM ───────────────────────────────────────────────────────────
        ssm.StringParameter(
            self, "CBProjectName",
            parameter_name="/football-cup/codebuild/coach_project_name",
            string_value=self.coach_build_project.project_name,
        )
        ssm.StringParameter(
            self, "CBSourceBucket",
            parameter_name="/football-cup/codebuild/source_bucket",
            string_value=source_bucket.bucket_name,
        )

        CfnOutput(self, "BuildProjectName", value=self.coach_build_project.project_name)
        CfnOutput(self, "BuildLogsUrl",
            value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home"
                  f"?region={self.region}#logsV2:log-groups/log-group/"
                  f"%2Faws%2Fcodebuild%2Ffootball-cup-coach-build")
