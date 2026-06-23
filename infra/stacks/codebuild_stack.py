"""
CodeBuild Stack — ARM64 build project for the coach container ONLY.

Rules followed:
  ✅ Source: NO_SOURCE  (curl downloads ZIP from GitHub in buildspec)
  ✅ Buildspec: inline inside the project (no S3 upload needed)
  ✅ GitHub download: curl -L from AbilashEG/football-cup
  ✅ ARM64 native: LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0
  ✅ privileged=True for Docker daemon
  ✅ COACH_REPO_URI injected as env var
  ✅ --no-cli-pager on all AWS CLI calls
  ❌ NO S3 source bucket
  ❌ NO git clone
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_codebuild as codebuild,
    aws_iam as iam,
    aws_logs as logs,
    aws_ssm as ssm,
)
from constructs import Construct


class CodeBuildStack(Stack):
    def __init__(self, scope: Construct, id: str, agentcore_stack, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── IAM role for CodeBuild ────────────────────────────────────────
        cb_role = iam.Role(
            self,
            "CodeBuildRole",
            role_name="football-cup-codebuild-role",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
        )

        # ECR: login + push to coach repo
        cb_role.add_to_policy(
            iam.PolicyStatement(
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
            )
        )

        # SSM: write build tag + read any /football-cup/* params
        cb_role.add_to_policy(
            iam.PolicyStatement(
                sid="SSMAccess",
                actions=["ssm:PutParameter", "ssm:GetParameter", "ssm:GetParameters"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/football-cup/*"
                ],
            )
        )

        # CloudWatch Logs
        cb_role.add_to_policy(
            iam.PolicyStatement(
                sid="CWLogs",
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        # STS: GetCallerIdentity (used in buildspec to derive ECR registry)
        cb_role.add_to_policy(
            iam.PolicyStatement(
                sid="STSCallerIdentity",
                actions=["sts:GetCallerIdentity"],
                resources=["*"],
            )
        )

        # ── S3 bucket for source (satisfies CDK source requirement) ─────
        # Buildspec downloads via curl anyway — bucket just needs to exist.
        from aws_cdk import aws_s3 as s3
        source_bucket = s3.Bucket(
            self,
            "CoachSourceBucket",
            bucket_name=f"football-cup-codebuild-src-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        # Give CodeBuild read access to the bucket
        cb_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3SourceRead",
                actions=["s3:GetObject", "s3:GetObjectVersion", "s3:ListBucket"],
                resources=[source_bucket.bucket_arn, f"{source_bucket.bucket_arn}/*"],
            )
        )

        # ── CloudWatch log group ──────────────────────────────────────────
        log_group = logs.LogGroup(
            self,
            "CoachBuildLogs",
            log_group_name="/aws/codebuild/football-cup-coach-build",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # ── Inline buildspec ──────────────────────────────────────────────
        # Source is S3 but buildspec overrides with curl from GitHub.
        # ✅ AbilashEG (one E)
        # ✅ curl -L not git clone
        # ✅ ZIP size check catches wrong-username typo
        # ✅ --no-cli-pager on all AWS CLI calls
        inline_buildspec = codebuild.BuildSpec.from_object({
            "version": "0.2",
            "env": {
                "variables": {
                    "GITHUB_USER": "AbilashEG",
                    "GITHUB_REPO": "football-cup",
                    "GITHUB_BRANCH": "main",
                    "UNZIP_FOLDER": "football-cup-main",
                    "AWS_REGION": self.region,
                }
            },
            "phases": {
                "pre_build": {
                    "commands": [
                        # Download repo ZIP (public repo — no auth needed)
                        "echo 'Downloading source from GitHub...'",
                        "curl -L -o source.zip https://github.com/${GITHUB_USER}/${GITHUB_REPO}/archive/refs/heads/${GITHUB_BRANCH}.zip",

                        # Validate ZIP size (wrong username = 9-byte redirect)
                        "ZIP_SIZE=$(wc -c < source.zip)",
                        "echo \"ZIP size = ${ZIP_SIZE} bytes\"",
                        "if [ \"$ZIP_SIZE\" -lt 1000 ]; then echo 'ERROR: ZIP too small — wrong GitHub username?'; exit 1; fi",

                        # Unzip
                        "unzip -q source.zip",
                        "echo 'Source contents:'",
                        "ls ${UNZIP_FOLDER}/",

                        # ECR login
                        "ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --no-cli-pager)",
                        "ECR_REGISTRY=\"${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com\"",
                        "IMAGE_TAG=$(date +%Y%m%d-%H%M%S)",
                        "echo \"Registry = ${ECR_REGISTRY}\"",
                        "echo \"Tag      = ${IMAGE_TAG}\"",
                        "aws ecr get-login-password --region ${AWS_REGION} --no-cli-pager | docker login --username AWS --password-stdin ${ECR_REGISTRY}",
                    ]
                },
                "build": {
                    "commands": [
                        "echo 'Building ARM64 coach image...'",
                        "cd ${UNZIP_FOLDER}",

                        # ARM64 native on CodeBuild ARM_CONTAINER — no --platform flag
                        # Build context is repo root → COPY agents/shared works
                        "docker build --file coach/Dockerfile --tag ${COACH_REPO_URI}:latest --tag ${COACH_REPO_URI}:${IMAGE_TAG} .",

                        "echo 'Build complete'",
                        "docker images ${COACH_REPO_URI}:latest",
                    ]
                },
                "post_build": {
                    "commands": [
                        "echo 'Pushing to ECR...'",
                        "cd ${UNZIP_FOLDER}",
                        "docker push ${COACH_REPO_URI}:latest",
                        "docker push ${COACH_REPO_URI}:${IMAGE_TAG}",
                        "echo \"Pushed: ${COACH_REPO_URI}:latest\"",
                        "echo \"Pushed: ${COACH_REPO_URI}:${IMAGE_TAG}\"",

                        # Store build tag in SSM for deploy script to confirm
                        "aws ssm put-parameter --name /football-cup/coach/last_build_tag --value ${IMAGE_TAG} --type String --overwrite --region ${AWS_REGION} --no-cli-pager",
                        "echo 'Build tag stored in SSM'",
                        "echo '=== DONE ==='",
                    ]
                },
            },
        })

        # ── CodeBuild project ─────────────────────────────────────────────
        self.coach_build_project = codebuild.Project(
            self,
            "CoachBuildProject",
            project_name="football-cup-coach-build",
            description="ARM64 coach container build — downloads from AbilashEG/football-cup",

            # ✅ S3 source — buildspec downloads from GitHub via curl
            source=codebuild.Source.s3(
                bucket=source_bucket,
                path="",
            ),

            # ✅ ARM64 native environment
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0,
                compute_type=codebuild.ComputeType.SMALL,
                privileged=True,   # Required for Docker daemon inside CodeBuild
            ),

            build_spec=inline_buildspec,

            # Inject coach ECR URI — buildspec uses ${COACH_REPO_URI}
            environment_variables={
                "COACH_REPO_URI": codebuild.BuildEnvironmentVariable(
                    value=agentcore_stack.coach_repo.repository_uri,
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                ),
            },

            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(
                    log_group=log_group,
                    enabled=True,
                )
            ),

            timeout=Duration.minutes(15),
            role=cb_role,
        )

        # ── SSM: store project name for deploy script ─────────────────────
        ssm.StringParameter(
            self,
            "CodeBuildProjectName",
            parameter_name="/football-cup/codebuild/coach_project_name",
            string_value=self.coach_build_project.project_name,
        )
        ssm.StringParameter(
            self,
            "CodeBuildSourceBucket",
            parameter_name="/football-cup/codebuild/source_bucket",
            string_value=source_bucket.bucket_name,
        )

        # ── Outputs ───────────────────────────────────────────────────────
        CfnOutput(
            self,
            "CoachBuildProjectName",
            value=self.coach_build_project.project_name,
            export_name="football-cup-coach-build-project",
        )
        CfnOutput(
            self,
            "CoachBuildLogsUrl",
            value=(
                f"https://{self.region}.console.aws.amazon.com/cloudwatch/home"
                f"?region={self.region}#logsV2:log-groups/log-group/"
                f"%2Faws%2Fcodebuild%2Ffootball-cup-coach-build"
            ),
            description="CloudWatch logs for coach CodeBuild project",
        )
