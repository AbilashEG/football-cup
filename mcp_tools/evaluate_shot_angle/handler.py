"""
MCP Tool: evaluate_shot_angle
Lambda ARM64 — calculates shot angle and checks if lane is clear.
Input:  { "shooter_position": {x, y}, "goal_center": {x, y} (optional, default right goal),
          "opponents": [{player_id, position: {x, y}}] }
Output: { "angle_degrees": float, "is_clear": bool, "blocked_by": str|None,
          "distance_to_goal": float, "recommended_aim": {x, y} }

Used by STR_01 before committing to SHOOT.
"""

import json
import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Default right goal posts
RIGHT_GOAL_CENTER = {"x": 29.0, "y": 0.0}
RIGHT_GOAL_TOP = {"x": 29.0, "y": 4.0}
RIGHT_GOAL_BOTTOM = {"x": 29.0, "y": -4.0}

SHOT_LANE_WIDTH = 1.5  # units — if an opponent is within this of the trajectory, shot is blocked


def handler(event: dict, context) -> dict:
    try:
        body = _parse_body(event)

        shooter = body.get("shooter_position", {})
        goal_center = body.get("goal_center", RIGHT_GOAL_CENTER)
        opponents = body.get("opponents", [])

        sx: float = float(shooter.get("x", 0.0))
        sy: float = float(shooter.get("y", 0.0))
        gx: float = float(goal_center.get("x", 29.0))
        gy: float = float(goal_center.get("y", 0.0))

        # Distance to goal
        distance_to_goal = math.sqrt((gx - sx) ** 2 + (gy - sy) ** 2)

        # Shot angle: angle subtended by goal posts at shooter position
        # Using right goal top & bottom posts
        goal_top_x = gx
        goal_top_y = 4.0
        goal_bot_x = gx
        goal_bot_y = -4.0

        angle_to_top = math.atan2(goal_top_y - sy, goal_top_x - sx)
        angle_to_bot = math.atan2(goal_bot_y - sy, goal_bot_x - sx)
        angle_degrees = abs(math.degrees(angle_to_top - angle_to_bot))

        # Check if shot lane is clear
        blocked_by: Optional[str] = None
        for opp in opponents:
            opp_x = float(opp["position"]["x"])
            opp_y = float(opp["position"]["y"])

            # Only opponents between shooter and goal matter
            if opp_x <= sx:
                continue

            # Point-to-line distance from opponent to shooter→goal vector
            lane_dist = _point_to_line_distance(sx, sy, gx, gy, opp_x, opp_y)

            # Also check the opponent is within the parametric range of the shot
            t = _parametric_t(sx, sy, gx, gy, opp_x, opp_y)

            if lane_dist < SHOT_LANE_WIDTH and 0.0 < t < 1.0:
                blocked_by = opp.get("player_id", "unknown")
                break

        is_clear = blocked_by is None

        # Best aim point: aim away from nearest post to open corner
        if sy >= 0:
            recommended_aim = {"x": gx, "y": -3.5}  # Aim low opposite side
        else:
            recommended_aim = {"x": gx, "y": 3.5}

        logger.info(
            f"evaluate_shot_angle: angle={angle_degrees:.1f}° dist={distance_to_goal:.1f} "
            f"clear={is_clear} blocked_by={blocked_by}"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "angle_degrees": round(angle_degrees, 2),
                    "is_clear": is_clear,
                    "blocked_by": blocked_by,
                    "distance_to_goal": round(distance_to_goal, 2),
                    "recommended_aim": recommended_aim,
                    "should_shoot": is_clear and angle_degrees > 20.0 and distance_to_goal < 20.0,
                }
            ),
        }

    except Exception as e:
        logger.error(f"evaluate_shot_angle error: {e}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def _point_to_line_distance(
    x1: float, y1: float, x2: float, y2: float, px: float, py: float
) -> float:
    """Perpendicular distance from point (px,py) to line segment (x1,y1)→(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    line_len_sq = dx * dx + dy * dy
    if line_len_sq == 0:
        return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
    numerator = abs(dy * px - dx * py + x2 * y1 - y2 * x1)
    return numerator / math.sqrt(line_len_sq)


def _parametric_t(
    x1: float, y1: float, x2: float, y2: float, px: float, py: float
) -> float:
    """Parametric t of closest point on line (x1,y1)→(x2,y2) to point (px,py)."""
    dx = x2 - x1
    dy = y2 - y1
    line_len_sq = dx * dx + dy * dy
    if line_len_sq == 0:
        return 0.0
    return ((px - x1) * dx + (py - y1) * dy) / line_len_sq


def _parse_body(event: dict) -> dict:
    if "body" in event and isinstance(event["body"], str):
        return json.loads(event["body"])
    if "body" in event and isinstance(event["body"], dict):
        return event["body"]
    return event
