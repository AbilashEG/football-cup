"""
MCP Tool: get_game_state
Lambda ARM64 — queries DynamoDB for full GameState at a given tick.
Input:  { "match_id": str, "tick": int }
Output: Full GameState JSON for that tick, or latest if tick omitted.
"""

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table(TABLE_NAME)


def handler(event: dict, context) -> dict:
    """
    Retrieves GameState from DynamoDB.
    PK = match_id (STRING), SK = tick (NUMBER).
    If tick is -1 or not provided, returns the latest tick.
    """
    try:
        body = event if isinstance(event, dict) else json.loads(event.get("body", "{}"))

        # Support both direct invocation and API Gateway proxy format
        if "body" in event and isinstance(event["body"], str):
            body = json.loads(event["body"])
        elif "body" in event and isinstance(event["body"], dict):
            body = event["body"]
        else:
            body = event

        match_id: str = body.get("match_id")
        tick: int = body.get("tick", -1)

        if not match_id:
            return _error(400, "match_id is required")

        if tick == -1:
            # Query latest tick: sort descending, limit 1
            response = table.query(
                KeyConditionExpression=Key("match_id").eq(match_id),
                ScanIndexForward=False,
                Limit=1,
            )
        else:
            response = table.query(
                KeyConditionExpression=Key("match_id").eq(match_id)
                & Key("tick").eq(tick),
                Limit=1,
            )

        items = response.get("Items", [])
        if not items:
            return _error(404, f"No game state found for match_id={match_id} tick={tick}")

        item = items[0]
        game_state = json.loads(item["game_state_json"])

        logger.info(
            f"get_game_state: match={match_id} tick={item.get('tick')} retrieved"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "match_id": match_id,
                    "tick": item.get("tick"),
                    "game_state": game_state,
                }
            ),
        }

    except Exception as e:
        logger.error(f"get_game_state error: {e}", exc_info=True)
        return _error(500, str(e))


def _error(status: int, message: str) -> dict:
    return {
        "statusCode": status,
        "body": json.dumps({"error": message}),
    }
