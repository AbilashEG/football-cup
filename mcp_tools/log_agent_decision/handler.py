"""
MCP Tool: log_agent_decision
Lambda ARM64 — appends TickEvent as NDJSON line to S3, updates DynamoDB latest action.
Input:  { "tick_event": TickEvent }
Output: { "logged": bool, "s3_key": str, "dynamodb_updated": bool }

Called by the tick engine after every agent decision resolves.
Also stores the latest game state snapshot in DynamoDB for real-time queries.
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
BUCKET_NAME = os.environ["BUCKET_NAME"]

s3 = boto3.client("s3", region_name="us-east-1")
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table(TABLE_NAME)


def handler(event: dict, context) -> dict:
    try:
        body = _parse_body(event)
        tick_event: dict = body.get("tick_event")

        if not tick_event:
            return _error(400, "tick_event is required")

        match_id: str = tick_event.get("match_id")
        tick: int = tick_event.get("tick", 0)
        player_id: str = tick_event.get("player_id")

        if not match_id:
            return _error(400, "tick_event.match_id is required")

        # --- S3: Append NDJSON line to event log ---
        s3_key = f"football-cup-events/{match_id}/events.ndjson"
        ndjson_line = json.dumps(tick_event, default=str) + "\n"

        # Use S3 GetObject + PutObject (append pattern via read-modify-write)
        # For high-throughput, a Kinesis Firehose would be better, but this
        # matches the Lambda-only constraint of the RFP reference system.
        existing_content = ""
        try:
            existing = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
            existing_content = existing["Body"].read().decode("utf-8")
        except s3.exceptions.NoSuchKey:
            existing_content = ""
        except Exception as e:
            logger.warning(f"S3 read warning (may be first event): {e}")
            existing_content = ""

        new_content = existing_content + ndjson_line
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=new_content.encode("utf-8"),
            ContentType="application/x-ndjson",
        )

        # --- DynamoDB: Store game state snapshot for this tick ---
        game_state_snapshot = tick_event.get("game_state_snapshot", {})

        # TTL: 7 days from now
        ttl = int(datetime.now(timezone.utc).timestamp()) + (7 * 24 * 60 * 60)

        table.put_item(
            Item={
                "match_id": match_id,
                "tick": tick,
                "player_id": player_id,
                "command": json.dumps(tick_event.get("command", {})),
                "latency_ms": str(tick_event.get("latency_ms", 0)),
                "game_state_json": json.dumps(game_state_snapshot),
                "timestamp": tick_event.get("timestamp", datetime.utcnow().isoformat()),
                "expires_at": ttl,
            }
        )

        logger.info(
            f"log_agent_decision: match={match_id} tick={tick} "
            f"player={player_id} s3_key={s3_key}"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "logged": True,
                    "s3_key": s3_key,
                    "dynamodb_updated": True,
                    "match_id": match_id,
                    "tick": tick,
                    "player_id": player_id,
                }
            ),
        }

    except Exception as e:
        logger.error(f"log_agent_decision error: {e}", exc_info=True)
        return _error(500, str(e))


def _parse_body(event: dict) -> dict:
    if "body" in event and isinstance(event["body"], str):
        return json.loads(event["body"])
    if "body" in event and isinstance(event["body"], dict):
        return event["body"]
    return event


def _error(status: int, message: str) -> dict:
    return {"statusCode": status, "body": json.dumps({"error": message})}
