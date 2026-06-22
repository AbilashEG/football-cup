"""
players/midfielder/handler.py
==============================
Lambda function — registered in AgentCore Gateway as MCP tool "player_mid".
Called by coach/agent.py every tick via boto3 direct invocation.
Returns ONE AgentCommand for MID_01.

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
from strands.models.bedrock import BedrockModel  # noqa: E402

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION_NAME", "us-east-1")
PLAYER_ID = "MID_01"

# ─── Agent initialised at cold start ─────────────────────────────────────────
mid_agent = Agent(
    model=BedrockModel(
        model_id="amazon.nova-micro-v1:0",
        region_name=REGION,
    ),
    system_prompt="""
You are MID_01, the MIDFIELDER — engine of the team.

DECISION PRIORITY (pick ONE command per tick):

1. PASS
   → When: you have ball AND clear forward channel to STR_01 exists
   → Condition: no opponent within 3 units of the passing lane
   → target_player_id: STR_01

2. PRESS_BALL
   → When: opponent has ball in midfield (|x| < 10) AND you are within 6 units
   → Goal: win the ball back immediately
   → Use aggressively — this is high value

3. INTERCEPT
   → When: ball moving through midfield zone you can reach within 2 ticks
   → target_position: projected intercept point

4. DRIBBLE
   → When: you have ball AND clear space ahead (no opponent within 4 units forward)
   → Prefer this over a backward PASS
   → target_position: space ahead toward STR_01

5. PASS (backward)
   → When: pressed, no forward option, DEF_L or DEF_R is open
   → target_player_id: DEF_L or DEF_R (whichever is less pressured)

6. MOVE_TO
   → When: off the ball — find open space, make yourself available
   → target_position: open channel between ball and STR_01

7. IDLE
   → Absolute last resort — almost never correct

HARD LIMITS:
- Do NOT always choose PASS — vary your commands
- PRESS_BALL and INTERCEPT are high value — use them aggressively
- If DRIBBLE is available, prefer it over a backward PASS
- Track both ball position and teammate positions each tick

Available commands: MOVE_TO, PASS, PRESS_BALL, DRIBBLE, INTERCEPT, IDLE
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

    my_pos_x    = my_player.position.x if my_player else 0.0
    my_pos_y    = my_player.position.y if my_player else 0.0
    my_stamina  = my_player.stamina    if my_player else 100.0
    my_has_ball = my_player.has_ball   if my_player else False

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

MY STATE (MID_01):
  position: ({my_pos_x:.1f}, {my_pos_y:.1f})
  stamina:  {my_stamina:.0f}%
  has_ball: {my_has_ball}

BALL:
  position: ({ball.position.x:.1f}, {ball.position.y:.1f})
  velocity: ({ball.velocity.vx:.2f}, {ball.velocity.vy:.2f})
  carrier:  {ball.last_touched_by or "loose"}

OPPONENTS:
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
        command: AgentCommand = mid_agent.structured_output(AgentCommand, prompt)
        logger.info("MID_01 → %s | %s", command.type, command.rationale)
        return command.model_dump()
    except Exception as e:
        logger.error("MID_01 handler error: %s", e)
        return {
            "type": "IDLE",
            "target_player_id": None,
            "target_position": None,
            "rationale": "MID error — IDLE this tick",
        }
