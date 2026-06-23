"""
players/striker/handler.py
===========================
Lambda function — registered in AgentCore Gateway as MCP tool "player_str".
Called by coach/agent.py every tick via boto3 direct invocation.
Returns ONE AgentCommand for STR_01.

NO FastAPI. NO Docker. Pure Lambda handler.
"""

import json
import logging
import os
import sys

sys.path.append("/var/task/shared")

from command_schema import AgentCommand, CommandType, Position  # noqa: E402
from game_state import GameState  # noqa: E402
from strands import Agent  # noqa: E402
from strands.models import BedrockModel  # noqa: E402

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION_NAME", "us-east-1")
PLAYER_ID = "STR_01"

# ─── Agent initialised at cold start ─────────────────────────────────────────
str_agent = Agent(
    model=BedrockModel(
        model_id="amazon.nova-micro-v1:0",
        region_name=REGION,
    ),
    system_prompt="""
You are STR_01, the STRIKER. Sole objective: SCORE GOALS.

DECISION PRIORITY (pick ONE command per tick):

1. SHOOT
   → When: you have ball AND distance to opponent goal < 15 AND shot angle > 20 degrees
   → target_position: {"x": 29.0, "y": 0.0}  (opponent goal center)
   → DO NOT hesitate — shoot early, shoot often

2. SHOOT (close range override)
   → When: you have ball AND distance to opponent goal < 8
   → Shoot regardless of angle — any shot is better than none

3. DRIBBLE
   → When: you have ball AND defender within 3 units AND space opens to one side
   → target_position: the open space past the defender

4. MOVE_TO (attacking run)
   → When: you do NOT have ball
   → Make a run BEHIND the defensive line
   → target_position: space with x > opponent last defender x

5. PRESS_BALL
   → When: opponent goalkeeper has ball (last_touched_by = opponent GK)
   → Pressure them into a mistake

6. PASS
   → When: completely blocked, no shoot or dribble path, MID_01 better positioned
   → ONLY use if absolutely no other option
   → target_player_id: MID_01

7. IDLE
   → NEVER choose this unless stamina < 5%

HARD LIMITS:
- NEVER track back past x = -5 (your half)
- SHOOT is almost always the right call when you have the ball
- Do NOT default to PASS when SHOOT is available
- Command diversity matters: use SHOOT, DRIBBLE, MOVE_TO, PRESS_BALL
- Conserve stamina only when ball is deep in opponent's far half

Available commands: MOVE_TO, PASS, SHOOT, DRIBBLE, PRESS_BALL, IDLE
rationale: one short line, max 12 words.
""",
)


def _build_prompt(game_state: GameState) -> str:
    my_player = next(
        (p for p in game_state.players if p.player_id == PLAYER_ID), None
    )
    ball = game_state.ball
    my_team_id = my_player.team_id if my_player else ""

    opponents = [p for p in game_state.players if p.team_id != my_team_id]
    teammates = [
        p for p in game_state.players
        if p.team_id == my_team_id and p.player_id != PLAYER_ID
    ]

    my_pos_x    = my_player.position.x if my_player else 10.0
    my_pos_y    = my_player.position.y if my_player else 0.0
    my_stamina  = my_player.stamina    if my_player else 100.0
    my_has_ball = my_player.has_ball   if my_player else False

    # Compute rough distance to opponent goal (x=29)
    dist_to_goal = abs(29.0 - my_pos_x)

    opponent_lines = "\n".join(
        f"  {p.player_id}: ({p.position.x:.1f},{p.position.y:.1f})"
        for p in opponents[:4]
    )
    teammate_lines = "\n".join(
        f"  {p.player_id}: ({p.position.x:.1f},{p.position.y:.1f})"
        for p in teammates
    )
    score_str = " | ".join(f"{s.team_name}:{s.goals}" for s in game_state.scores)
    hint_line = f"\nCOACH HINT: {game_state.human_hint}" if game_state.human_hint else ""

    return f"""TICK {game_state.tick} | CLOCK {game_state.clock_seconds}s
SCORE: {score_str}

MY STATE (STR_01):
  position:       ({my_pos_x:.1f}, {my_pos_y:.1f})
  stamina:        {my_stamina:.0f}%
  has_ball:       {my_has_ball}
  dist_to_goal:   {dist_to_goal:.1f} units

BALL:
  position: ({ball.position.x:.1f}, {ball.position.y:.1f})
  velocity: ({ball.velocity.vx:.2f}, {ball.velocity.vy:.2f})
  carrier:  {ball.last_touched_by or "loose"}

OPPONENTS (defenders to beat):
{opponent_lines}

MY TEAMMATES:
{teammate_lines}{hint_line}

Issue ONE AgentCommand JSON now.
"""


def handler(event, context):
    """
    Lambda entry point invoked by coach/agent.py via boto3.
    event: { "game_state": { ...GameState dict... } }
    returns: AgentCommand dict
    """
    try:
        game_state_data = event.get("game_state", event)
        game_state = GameState(**game_state_data)
        prompt = _build_prompt(game_state)
        command: AgentCommand = str_agent.structured_output(AgentCommand, prompt)
        logger.info("STR_01 → %s | %s", command.type, command.rationale)
        return command.model_dump()
    except Exception as e:
        logger.error("STR_01 handler error: %s", e)
        return {
            "type": "IDLE",
            "target_player_id": None,
            "target_position": None,
            "rationale": "STR error — IDLE this tick",
        }
