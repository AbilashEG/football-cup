"""
MCP Tool: get_nearest_opponent
Lambda ARM64 — Euclidean distance from a player to all opponents.
Input:  { "player_id": str, "game_state": GameState }
Output: { "nearest_opponent_id": str, "distance": float, "position": {x, y},
          "all_opponents_sorted": [{player_id, distance, position}] }

Used by DEF_L, DEF_R for marking decisions and MID_01 for press decisions.
"""

import json
import logging
import math

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def handler(event: dict, context) -> dict:
    try:
        body = _parse_body(event)

        player_id: str = body.get("player_id")
        game_state: dict = body.get("game_state", {})

        if not player_id:
            return _error(400, "player_id is required")
        if not game_state:
            return _error(400, "game_state is required")

        players = game_state.get("players", [])

        # Find the requesting player
        my_player = next((p for p in players if p["player_id"] == player_id), None)
        if not my_player:
            return _error(404, f"Player {player_id} not found in game_state")

        my_x = my_player["position"]["x"]
        my_y = my_player["position"]["y"]
        my_team = my_player["team_id"]

        # All opponents
        opponents = [p for p in players if p["team_id"] != my_team]
        if not opponents:
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "nearest_opponent_id": None,
                        "distance": None,
                        "position": None,
                        "all_opponents_sorted": [],
                    }
                ),
            }

        # Sort by Euclidean distance
        def dist(p) -> float:
            dx = p["position"]["x"] - my_x
            dy = p["position"]["y"] - my_y
            return math.sqrt(dx * dx + dy * dy)

        sorted_opponents = sorted(opponents, key=dist)
        nearest = sorted_opponents[0]
        nearest_dist = dist(nearest)

        all_sorted = [
            {
                "player_id": p["player_id"],
                "distance": round(dist(p), 2),
                "position": p["position"],
                "has_ball": p.get("has_ball", False),
                "stamina": p.get("stamina", 100),
            }
            for p in sorted_opponents
        ]

        logger.info(
            f"get_nearest_opponent: {player_id} → nearest={nearest['player_id']} "
            f"dist={nearest_dist:.2f}"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "nearest_opponent_id": nearest["player_id"],
                    "distance": round(nearest_dist, 2),
                    "position": nearest["position"],
                    "has_ball": nearest.get("has_ball", False),
                    "all_opponents_sorted": all_sorted,
                }
            ),
        }

    except Exception as e:
        logger.error(f"get_nearest_opponent error: {e}", exc_info=True)
        return _error(500, str(e))


def _parse_body(event: dict) -> dict:
    if "body" in event and isinstance(event["body"], str):
        return json.loads(event["body"])
    if "body" in event and isinstance(event["body"], dict):
        return event["body"]
    return event


def _error(status: int, message: str) -> dict:
    return {"statusCode": status, "body": json.dumps({"error": message})}
