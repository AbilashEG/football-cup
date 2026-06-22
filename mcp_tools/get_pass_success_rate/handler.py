"""
MCP Tool: get_pass_success_rate
Lambda ARM64 — reads S3 NDJSON event log, computes historical pass success rate.
Input:  { "from_player_id": str, "to_player_id": str, "match_id": str }
Output: { "success_rate": float, "total_attempts": int, "successful": int,
          "recent_form": str, "recommendation": str }

Used by MID_01 for intelligent pass target selection.
Pass is "successful" if the target player next touched the ball within 3 ticks.
"""

import json
import logging
import os
from io import StringIO

import boto3

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

BUCKET_NAME = os.environ["BUCKET_NAME"]
s3 = boto3.client("s3", region_name="us-east-1")


def handler(event: dict, context) -> dict:
    try:
        body = _parse_body(event)

        from_player: str = body.get("from_player_id")
        to_player: str = body.get("to_player_id")
        match_id: str = body.get("match_id")

        if not all([from_player, to_player, match_id]):
            return _error(400, "from_player_id, to_player_id, and match_id are required")

        s3_key = f"football-cup-events/{match_id}/events.ndjson"

        # Fetch NDJSON log from S3
        try:
            response = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
            raw = response["Body"].read().decode("utf-8")
        except s3.exceptions.NoSuchKey:
            # No events yet — return neutral stats
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "success_rate": 0.5,
                        "total_attempts": 0,
                        "successful": 0,
                        "recent_form": "no_data",
                        "recommendation": f"No historical data. Default 50% estimate.",
                    }
                ),
            }

        events = [json.loads(line) for line in raw.strip().splitlines() if line.strip()]

        # Find all PASS commands from_player → to_player
        total_attempts = 0
        successful = 0
        recent_results: list[bool] = []

        for i, evt in enumerate(events):
            cmd = evt.get("command", {})
            if (
                cmd.get("type") == "PASS"
                and evt.get("player_id") == from_player
                and cmd.get("target_player_id") == to_player
            ):
                total_attempts += 1

                # Success: check if to_player appears as "last_touched_by" in next 3 ticks
                tick_of_pass = evt.get("tick", 0)
                success = False
                for j in range(i + 1, min(i + 4, len(events))):
                    future_evt = events[j]
                    snap = future_evt.get("game_state_snapshot", {})
                    ball = snap.get("ball", {})
                    if ball.get("last_touched_by") == to_player:
                        success = True
                        break

                if success:
                    successful += 1
                    recent_results.append(True)
                else:
                    recent_results.append(False)

        success_rate = (successful / total_attempts) if total_attempts > 0 else 0.5

        # Recent form: last 5 passes
        last_5 = recent_results[-5:] if len(recent_results) >= 5 else recent_results
        recent_successes = sum(last_5)
        if len(last_5) == 0:
            recent_form = "no_data"
        elif recent_successes / len(last_5) >= 0.6:
            recent_form = "good"
        elif recent_successes / len(last_5) >= 0.4:
            recent_form = "mixed"
        else:
            recent_form = "poor"

        recommendation = (
            f"Pass {from_player}→{to_player}: {success_rate*100:.0f}% success "
            f"({successful}/{total_attempts}), recent form: {recent_form}"
        )

        logger.info(
            f"get_pass_success_rate: {from_player}→{to_player} "
            f"rate={success_rate:.2f} attempts={total_attempts}"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "success_rate": round(success_rate, 3),
                    "total_attempts": total_attempts,
                    "successful": successful,
                    "recent_form": recent_form,
                    "recommendation": recommendation,
                }
            ),
        }

    except Exception as e:
        logger.error(f"get_pass_success_rate error: {e}", exc_info=True)
        return _error(500, str(e))


def _parse_body(event: dict) -> dict:
    if "body" in event and isinstance(event["body"], str):
        return json.loads(event["body"])
    if "body" in event and isinstance(event["body"], dict):
        return event["body"]
    return event


def _error(status: int, message: str) -> dict:
    return {"statusCode": status, "body": json.dumps({"error": message})}
