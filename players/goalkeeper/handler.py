"""
players/goalkeeper/handler.py
==============================
Lambda function — registered in AgentCore Gateway as MCP tool "player_gk".
Called by coach/agent.py every tick via boto3 direct invocation.
Returns ONE AgentCommand for GK_01.

NO FastAPI. NO Docker. Pure Lambda handler.
"""

import json
import logging
import os
import sys

sys.path.append("/var/task/shared")   # bundled alongside handler at deploy time

from command_schema import AgentCommand, CommandType, Position  # noqa: E402
from game_state import GameState  # noqa: E402
from strands import Agent  # noqa: E402
from strands.models.bedrock import BedrockModel  # noqa: E402

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION_NAME", "us-east-1")

# ─── Agent initialised at cold start — not per invocation ────────────────────
gk_agent = Agent(
    model=BedrockModel(
        model_id="amazon.nova-micro-v1:0",
        region_name=REGION,
    ),
    system_prompt="""
You are GK_01, the GOALKEEPER for your team.
YOUR GOAL: Protect the left goal (x = -29, y = 0).

DECISION PRIORITY (pick ONE command per tick):

1. GOALKEEPER_DIVE
   → When: ball.velocity.vx < -4 AND ball.position.x < -10
   → Goal: intercept incoming shot
   → target_position: predicted ball interception point

2. CLEAR
   → When: ball inside penalty box (x < -22, |y| < 10) AND you can reach it
   → Goal: boot ball away from danger
   → target_position: midfield (x=0, y=0)

3. PASS
   → When: you have the ball (has_ball=True)
   → Goal: give ball to nearest defender safely
   → target_player_id: DEF_L or DEF_R (whichever is closer)

4. MOVE_TO
   → When: repositioning between threats
   → Goal: stay between ball and goal center
   → target_position: x=-27, y=clamp(ball.y * 0.3, -4, 4)

5. IDLE
   → When: ball is far (x > 15) AND no threat approaching
   → Last resort only

HARD LIMITS:
- NEVER go past x = -12
- NEVER SHOOT
- NEVER DRIBBLE into opponent territory
- Always protect the goal first

Respond with AgentCommand JSON only.
type must be one of: GOALKEEPER_DIVE, CLEAR, PASS, MOVE_TO, IDLE
rationale: one short line, max 12 words.
""",
)


def _build_prompt(game_state: GameState) -> str:
    my_player = next(
        (p for p in game_state.players if p.player_id == "GK_01"), None
    )
    ball = game_state.ball
    my_team_id = my_player.team_id if my_player else ""

    opponents = [p for p in game_state.players if p.team_id != my_team_id]
    teammates = [
        p for p in game_state.players
        if p.team_id == my_team_id and p.player_id != "GK_01"
    ]

    my_pos_x   = my_player.position.x if my_player else -28.0
    my_pos_y   = my_player.position.y if my_player else 0.0
    my_stamina = my_player.stamina    if my_player else 100.0
    my_has_ball = my_player.has_ball  if my_player else False

    opponent_lines = "\n".join(
        f"  {p.player_id}: ({p.position.x:.1f},{p.position.y:.1f})"
        for p in opponents[:3]
    )
    teammate_lines = "\n".join(
        f"  {p.player_id}: ({p.position.x:.1f},{p.position.y:.1f})"
        for p in teammates
    )
    score_str = " | ".join(f"{s.team_name}:{s.goals}" for s in game_state.scores)
    hint_line = f"\nCOACH HINT: {game_state.human_hint}" if game_state.human_hint else ""

    return f"""TICK {game_state.tick} | CLOCK {game_state.clock_seconds}s
SCORE: {score_str}

MY STATE (GK_01):
  position: ({my_pos_x:.1f}, {my_pos_y:.1f})
  stamina:  {my_stamina:.0f}%
  has_ball: {my_has_ball}

BALL:
  position: ({ball.position.x:.1f}, {ball.position.y:.1f})
  velocity: ({ball.velocity.vx:.2f}, {ball.velocity.vy:.2f})
  carrier:  {ball.last_touched_by or "loose"}

NEAREST OPPONENTS:
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
        command: AgentCommand = gk_agent.structured_output(AgentCommand, prompt)
        logger.info("GK_01 → %s | %s", command.type, command.rationale)
        return command.model_dump()
    except Exception as e:
        logger.error("GK_01 handler error: %s", e)
        return {
            "type": "IDLE",
            "target_player_id": None,
            "target_position": None,
            "rationale": "GK error — IDLE this tick",
        }
