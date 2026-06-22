"""
Storage Stack — DynamoDB tables + S3 event bucket.

Resources:
  - football-game-state   DynamoDB table (PK=match_id, SK=tick)
  - football-squads        DynamoDB table (PK=squad_id)
  - football-ws-connections DynamoDB table (PK=connection_id) with GSI on match_id
  - football-cup-events-{account} S3 bucket (NDJSON event logs)
"""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    CfnOutput,
)
from constructs import Construct


class StorageStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── DynamoDB: game state ──────────────────────────────────────────
        self.game_state_table = dynamodb.Table(
            self,
            "GameStateTable",
            table_name="football-game-state",
            partition_key=dynamodb.Attribute(
                name="match_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="tick", type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="expires_at",
            point_in_time_recovery=False,
        )

        # ── DynamoDB: squads ──────────────────────────────────────────────
        self.squads_table = dynamodb.Table(
            self,
            "SquadsTable",
            table_name="football-squads",
            partition_key=dynamodb.Attribute(
                name="squad_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── DynamoDB: WebSocket connections ───────────────────────────────
        self.ws_connections_table = dynamodb.Table(
            self,
            "WsConnectionsTable",
            table_name="football-ws-connections",
            partition_key=dynamodb.Attribute(
                name="connection_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="expires_at",
        )

        # GSI on match_id so broadcaster can query all connections for a match
        self.ws_connections_table.add_global_secondary_index(
            index_name="match_id-index",
            partition_key=dynamodb.Attribute(
                name="match_id", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ── S3: event log bucket ──────────────────────────────────────────
        self.events_bucket = s3.Bucket(
            self,
            "EventsBucket",
            bucket_name=f"football-cup-events-{self.account}",
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldEvents",
                    expiration=Duration.days(7),
                    enabled=True,
                )
            ],
        )

        # ── Outputs ───────────────────────────────────────────────────────
        CfnOutput(self, "GameStateTableName", value=self.game_state_table.table_name)
        CfnOutput(self, "SquadsTableName", value=self.squads_table.table_name)
        CfnOutput(self, "WsConnectionsTableName", value=self.ws_connections_table.table_name)
        CfnOutput(self, "EventsBucketName", value=self.events_bucket.bucket_name)
