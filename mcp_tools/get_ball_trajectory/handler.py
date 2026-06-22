"""
MCP Tool: get_ball_trajectory
Lambda ARM64 — pure math projection of ball position N ticks forward.
Input:  { "ball_position": {x, y}, "ball_velocity": {vx, vy}, "steps": int }
Output: { "predicted_positions": [{x, y, tick}], "will_reach_goal": bool, "goal_side": str|None }

Used by GK_01 to predict incoming shots before committing to GOALKEEPER_DIVE.
"""

import json
import logging
import math

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Physics constants matching backend/physics.py
BALL_FRICTION = 0.82
PITCH_X_MIN = -30.0
PITCH_X_MAX = 30.0
PITCH_Y_MIN = -20.0
PITCH_Y_MAX = 20.0
GOAL_HALF_WIDTH = 4.0  # |y| <= 4 is a goal


def handler(event: dict, context) -> dict:
    try:
        body = _parse_body(event)

        ball_pos = body.get("ball_position", {})
        ball_vel = body.get("ball_velocity", {})
        steps: int = min(int(body.get("steps", 10)), 30)  # cap at 30 ticks

        bx: float = float(ball_pos.get("x", 0.0))
        by: float = float(ball_pos.get("y", 0.0))
        vx: float = float(ball_vel.get("vx", 0.0))
        vy: float = float(ball_vel.get("vy", 0.0))

        predicted_positions = []
        will_reach_goal = False
        goal_side = None

        for step in range(1, steps + 1):
            bx = max(PITCH_X_MIN, min(PITCH_X_MAX, bx + vx))
            by = max(PITCH_Y_MIN, min(PITCH_Y_MAX, by + vy))
            vx *= BALL_FRICTION
            vy *= BALL_FRICTION

            predicted_positions.append(
                {"x": round(bx, 2), "y": round(by, 2), "tick": step}
            )

            # Check left goal (x <= -29, |y| <= 4)
            if bx <= -29.0 and abs(by) <= GOAL_HALF_WIDTH:
                will_reach_goal = True
                goal_side = "left"
                break

            # Check right goal (x >= 29, |y| <= 4)
            if bx >= 29.0 and abs(by) <= GOAL_HALF_WIDTH:
                will_reach_goal = True
                goal_side = "right"
                break

            # Stop if ball is essentially stationary
            if abs(vx) < 0.05 and abs(vy) < 0.05:
                break

        # Compute speed for context
        current_speed = math.sqrt(
            float(ball_vel.get("vx", 0.0)) ** 2 + float(ball_vel.get("vy", 0.0)) ** 2
        )

        logger.info(
            f"get_ball_trajectory: steps={len(predicted_positions)} "
            f"will_reach_goal={will_reach_goal} goal_side={goal_side}"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "predicted_positions": predicted_positions,
                    "will_reach_goal": will_reach_goal,
                    "goal_side": goal_side,
                    "ticks_to_goal": len(predicted_positions) if will_reach_goal else None,
                    "current_speed": round(current_speed, 2),
                }
            ),
        }

    except Exception as e:
        logger.error(f"get_ball_trajectory error: {e}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def _parse_body(event: dict) -> dict:
    if "body" in event and isinstance(event["body"], str):
        return json.loads(event["body"])
    if "body" in event and isinstance(event["body"], dict):
        return event["body"]
    return event
