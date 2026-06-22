"""
WebSocket broadcaster — pushes GameState updates to all connected frontend clients.

Architecture:
- API Gateway WebSocket API manages connection lifecycle (connect/disconnect/default)
- Connection IDs stored in DynamoDB websocket-connections table
- Broadcaster uses boto3 ApiGatewayManagementApi to POST to each connection
- Stale connections (410 Gone) are pruned from DynamoDB automatically

Matches the WebSocket + EventBridge pattern from the AWS Team Tracker reference system.
"""

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from game_state import GameState

logger = logging.getLogger(__name__)

WS_ENDPOINT_URL = os.environ.get("WS_ENDPOINT_URL", "")
WS_TABLE_NAME = os.environ.get("WS_TABLE_NAME", "football-ws-connections")
REGION = os.environ.get("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
ws_table = dynamodb.Table(WS_TABLE_NAME)

# Lazily initialised — requires WS_ENDPOINT_URL to be set at runtime
_apigw_client = None


def _get_apigw_client():
    global _apigw_client
    if _apigw_client is None:
        if not WS_ENDPOINT_URL:
            logger.warning("WS_ENDPOINT_URL not set — WebSocket broadcast disabled")
            return None
        _apigw_client = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=WS_ENDPOINT_URL,
            region_name=REGION,
        )
    return _apigw_client


async def broadcast_game_state(match_id: str, game_state: GameState) -> None:
    """
    Broadcast the current GameState to all WebSocket connections subscribed
    to the given match_id.

    Message format:
      { "type": "game_state", "payload": <GameState as JSON> }
    """
    apigw = _get_apigw_client()
    if not apigw:
        return

    connection_ids = _get_connections_for_match(match_id)
    if not connection_ids:
        return

    message = json.dumps(
        {
            "type": "game_state",
            "payload": game_state.model_dump(mode="json"),
        },
        default=str,
    ).encode("utf-8")

    stale_connections: list[str] = []

    for connection_id in connection_ids:
        try:
            apigw.post_to_connection(
                ConnectionId=connection_id,
                Data=message,
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("GoneException", "410"):
                # Client disconnected — mark for cleanup
                stale_connections.append(connection_id)
                logger.debug(f"Stale WS connection {connection_id} — will prune")
            else:
                logger.warning(
                    f"WS post_to_connection error [{error_code}] "
                    f"connection={connection_id}: {e}"
                )
        except Exception as e:
            logger.error(f"WS broadcast error for {connection_id}: {e}")

    # Prune stale connections
    for connection_id in stale_connections:
        _remove_connection(connection_id)


async def broadcast_tick_event(match_id: str, tick_event_payload: dict) -> None:
    """
    Broadcast a single TickEvent to the Agent Decision Feed.
    Sent separately from game_state so the frontend can display
    the rationale stream in real time without re-rendering the pitch.
    """
    apigw = _get_apigw_client()
    if not apigw:
        return

    connection_ids = _get_connections_for_match(match_id)
    if not connection_ids:
        return

    message = json.dumps(
        {
            "type": "tick_event",
            "payload": tick_event_payload,
        },
        default=str,
    ).encode("utf-8")

    for connection_id in connection_ids:
        try:
            apigw.post_to_connection(
                ConnectionId=connection_id,
                Data=message,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] in ("GoneException", "410"):
                _remove_connection(connection_id)
        except Exception as e:
            logger.error(f"WS tick_event broadcast error for {connection_id}: {e}")


def _get_connections_for_match(match_id: str) -> list[str]:
    """
    Query DynamoDB for all active WebSocket connections watching this match.
    Table schema: PK=connection_id, attribute match_id (GSI on match_id).
    """
    try:
        response = ws_table.query(
            IndexName="match_id-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("match_id").eq(match_id),
        )
        return [item["connection_id"] for item in response.get("Items", [])]
    except Exception as e:
        logger.error(f"_get_connections_for_match error: {e}")
        return []


def _remove_connection(connection_id: str) -> None:
    """Remove a stale/disconnected connection from DynamoDB."""
    try:
        ws_table.delete_item(Key={"connection_id": connection_id})
        logger.info(f"Pruned stale WS connection: {connection_id}")
    except Exception as e:
        logger.error(f"_remove_connection error for {connection_id}: {e}")


# ── WebSocket Lambda handler (connect / disconnect / default) ────────────────

def websocket_handler(event: dict, context) -> dict:
    """
    Lambda handler for API Gateway WebSocket events.
    Registered as the $connect, $disconnect, and $default route handler.
    """
    route_key = event.get("requestContext", {}).get("routeKey", "")
    connection_id = event.get("requestContext", {}).get("connectionId", "")

    if route_key == "$connect":
        query = event.get("queryStringParameters") or {}
        match_id = query.get("matchId", "global")
        _register_connection(connection_id, match_id)
        logger.info(f"WS $connect: connection={connection_id} match={match_id}")
        return {"statusCode": 200, "body": "Connected"}

    elif route_key == "$disconnect":
        _remove_connection(connection_id)
        logger.info(f"WS $disconnect: connection={connection_id}")
        return {"statusCode": 200, "body": "Disconnected"}

    elif route_key == "$default":
        # Handle coach hints sent from the frontend
        body_raw = event.get("body", "{}")
        try:
            body = json.loads(body_raw)
            msg_type = body.get("type", "")
            if msg_type == "coach_hint":
                _handle_coach_hint(
                    connection_id=connection_id,
                    match_id=body.get("matchId"),
                    hint=body.get("hint", ""),
                )
        except json.JSONDecodeError:
            pass
        return {"statusCode": 200, "body": "OK"}

    return {"statusCode": 400, "body": "Unknown route"}


def _register_connection(connection_id: str, match_id: str) -> None:
    """Store new WebSocket connection in DynamoDB."""
    import time
    try:
        ws_table.put_item(
            Item={
                "connection_id": connection_id,
                "match_id": match_id,
                "connected_at": int(time.time()),
                "expires_at": int(time.time()) + 3600,  # TTL: 1 hour
            }
        )
    except Exception as e:
        logger.error(f"_register_connection error: {e}")


def _handle_coach_hint(connection_id: str, match_id: str, hint: str) -> None:
    """
    Store coach hint in DynamoDB game-state table so tick engine picks it up.
    The tick engine reads human_hint from game state each tick.
    """
    if not match_id or not hint:
        return

    game_table_name = os.environ.get("TABLE_NAME", "football-game-state")
    game_table = boto3.resource("dynamodb", region_name=REGION).Table(game_table_name)

    try:
        # Update the latest tick item for this match with the hint
        game_table.update_item(
            Key={"match_id": match_id, "tick": -1},  # Sentinel item for live hints
            UpdateExpression="SET human_hint = :hint",
            ExpressionAttributeValues={":hint": hint[:200]},
        )
        logger.info(
            f"Coach hint stored: match={match_id} hint='{hint[:50]}' "
            f"from connection={connection_id}"
        )
    except Exception as e:
        logger.error(f"_handle_coach_hint error: {e}")
