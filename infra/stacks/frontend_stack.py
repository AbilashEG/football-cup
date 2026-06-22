"""
Frontend Stack — AWS Amplify app hosting for the Next.js 14 frontend.

Amplify pulls from GitHub, builds with `npm run build`, and hosts on CDN.
Environment variables (API URL, WS URL) are injected from SSM at build time.
"""

from aws_cdk import (
    CfnOutput,
    SecretValue,
    Stack,
    aws_amplify_alpha as amplify,
    aws_codebuild as codebuild,
    aws_iam as iam,
    aws_ssm as ssm,
)
from constructs import Construct


class FrontendStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        backend_stack,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── Read backend URLs from SSM ─────────────────────────────────────
        api_url = ssm.StringParameter.value_for_string_parameter(
            self, "/football-cup/backend/api_url"
        )
        ws_url = ssm.StringParameter.value_for_string_parameter(
            self, "/football-cup/backend/ws_url"
        )

        # ── Amplify App ────────────────────────────────────────────────────
        # GitHub token stored in SSM SecureString /football-cup/github_token
        github_token = SecretValue.ssm_secure(
            "/football-cup/github_token", version="1"
        )

        amplify_app = amplify.App(
            self,
            "FootballCupFrontend",
            app_name="football-cup-frontend",
            source_code_provider=amplify.GitHubSourceCodeProvider(
                owner="YOUR_GITHUB_ORG",
                repository="football-cup",
                oauth_token=github_token,
            ),
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "1.0",
                    "applications": [
                        {
                            "frontend": {
                                "phases": {
                                    "preBuild": {
                                        "commands": [
                                            "cd frontend",
                                            "npm ci",
                                        ]
                                    },
                                    "build": {
                                        "commands": ["npm run build"]
                                    },
                                },
                                "artifacts": {
                                    "baseDirectory": "frontend/.next",
                                    "files": ["**/*"],
                                },
                                "cache": {
                                    "paths": ["frontend/node_modules/**/*"]
                                },
                            },
                            "appRoot": "frontend",
                        }
                    ],
                }
            ),
            environment_variables={
                "NEXT_PUBLIC_API_URL": api_url,
                "NEXT_PUBLIC_WS_URL": ws_url,
                "NEXT_PUBLIC_AWS_REGION": self.region,
                "_LIVE_UPDATES": '[{"name":"Next.js version","pkg":"@aws-amplify/cli","type":"npm","version":"latest"}]',
            },
            platform=amplify.Platform.WEB_COMPUTE,  # SSR support
        )

        # ── Amplify Branch: main ───────────────────────────────────────────
        main_branch = amplify_app.add_branch(
            "main",
            branch_name="main",
            stage=amplify.BranchOptions(stage="PRODUCTION"),
            auto_build=True,
        )

        # ── Outputs ────────────────────────────────────────────────────────
        CfnOutput(
            self,
            "AmplifyAppId",
            value=amplify_app.app_id,
        )
        CfnOutput(
            self,
            "AmplifyAppUrl",
            value=f"https://main.{amplify_app.app_id}.amplifyapp.com",
            export_name="football-cup-frontend-url",
        )
