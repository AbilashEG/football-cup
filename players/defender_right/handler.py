"""
players/defender_right/handler.py
==================================
Lambda function — registered in AgentCore Gateway as MCP tool "player_def_r".
Called by coach/agent.py every tick via boto3 direct invocation.
Returns ONE AgentCommand for DEF_R.

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
PLAYER_ID = "DEF_R"

# ─── Agent initialised at cold start ─────────────────────────────────────────
def_r_agent = Agent(
    model=BedrockModel(
        model_id="amazon.nova-micro-v1:0",
        region_name=REGION,
    ),
    system_prompt="""
You are DEF_R, the RIGHT DEFENDER for your team.

DECISION PRIORITY (pick ONE command per tick):

1. TACKLE
   → When: opponent with ball is within 2.5 units of you
   → target_player_id: the opponent carrying the ball

2. INTERCEPT
   → When: ball moving toward your goal (vx < -1), you can reach the intercept point
   → target_position: projected ball path intercept point

3. MARK
   → When: opposing striker (STR_01) is in your half (x < 0)
   → target_player_id: STR_01 (opposing striker)
   → Goal: stay within 3 units of them to deny space

4. CLEAR
   → When: ball inside penalty box (x < -22, |y| < 10) and you reach it first
   → target_position: midfield (x=0, y=0)

5. PASS
   → When: you have the ball (has_ball=True) AND MID_01 is open ahead
   → target_player_id: MID_01
   → Goal: recycle possession forward

6. MOVE_TO
   → When: holding defensive shape
   → target_position: between ball and goal, x = -15 to -5 zone

7. IDLE
   → Last resort only

HARD LIMITS:
- NEVER push past x = +5 (halfway line) unless score demands it AND clock < 20s
- NEVER SHOOT (not your role)
- Always track the ball AND nearest opponent simultaneously
- Prioritise defensive duties over attacking support
- DEF_R covers the RIGHT flank — track opponents approaching from the right side

Available commands: MOVE_TO, PASS, MARK, INTERCEPT, TACKLE, CLEAR, IDLE
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
    my_pos_y    = my_player.position.y if my_player else 5.0
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

MY STATE (DEF_R):
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
        command: AgentCommand = def_r_agent.structured_output(AgentCommand, prompt)
        logger.info("DEF_R → %s | %s", command.type, command.rationale)
        return command.model_dump()
    except Exception as e:
        logger.error("DEF_R handler error: %s", e)
        return {
            "type": "IDLE",
            "target_player_id": None,
            "target_position": None,
            "rationale": "DEF_R error — IDLE this tick",
        }
