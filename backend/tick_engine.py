"""
Core 2-second tick loop.
Invokes all 5 agents in parallel, applies physics, detects goals,
broadcasts updated GameState via WebSocket, logs TickEvent to S3.
Runs as asyncio background task inside FastAPI Lambda.
"""

import asyncio
import logging
from datetime import datetime, timezone

from agentcore_client import invoke_all_agents_parallel
from game_state import GamePhase, GameState, PlayerState, Position, TickEvent, Velocity
from match_logger import log_match_summary, log_tick_event
from physics import apply_commands, detect_goal, update_ball_physics
from websocket_broadcaster import broadcast_game_state

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 2.0    # Decision point every 2 seconds
MATCH_DURATION_TICKS = 60      # 60 ticks × 2s = 120s = 2-minute match
HALF_TIME_TICK = 30            # Ticks per half
HALF_TIME_BREAK_SECONDS = 5.0  # Pause at half time
STAMINA_ACTIVE_DRAIN = 0.4     # Per tick for non-IDLE actions
STAMINA_IDLE_DRAIN = 0.1       # Per tick for IDLE

# Base kickoff positions (team A faces right, attacks right goal)
BASE_POSITIONS: dict[str, tuple[float, float]] = {
    "GK_01":  (-28.0,  0.0),
    "DEF_L":  (-15.0, -7.0),
    "DEF_R":  (-15.0,  7.0),
    "MID_01": (  0.0,  0.0),
    "STR_01": ( 12.0,  0.0),
}


async def run_match(match_id: str, game_state: GameState) -> GameState:
    """
    Full match lifecycle — runs 60 ticks × 2s.
    Returns final GameState with scores, phase=FULL_TIME.
    """
    game_state.phase = GamePhase.FIRST_HALF
    logger.info(f"Match {match_id} kicked off — {MATCH_DURATION_TICKS} ticks")

    for tick in range(MATCH_DURATION_TICKS):
        tick_start = asyncio.get_event_loop().time()

        game_state.tick = tick
        game_state.clock_seconds = tick * 2

        # ── Invoke all 5 agents in parallel ─────────────────────────────
        agent_results = await invoke_all_agents_parallel(
            game_state, match_session_id=match_id
        )

        # ── Apply commands → update positions, ball ──────────────────────
        game_state = apply_commands(game_state, agent_results)
        game_state = update_ball_physics(game_state)

        # ── Goal detection ───────────────────────────────────────────────
        scoring_team = detect_goal(game_state)
        if scoring_team:
            score = next(
                (s for s in game_state.scores if s.team_id == scoring_team), None
            )
            if score:
                score.goals += 1
            logger.info(
                f"GOAL tick={tick} team={scoring_team} "
                f"scores={[(s.team_name, s.goals) for s in game_state.scores]}"
            )
            game_state = _reset_to_kickoff(game_state, scored_by=scoring_team)

        # ── Stamina drain ────────────────────────────────────────────────
        for player in game_state.players:
            result = agent_results.get(player.player_id)
            if result and result[0].type.value != "IDLE":
                player.stamina = max(0.0, player.stamina - STAMINA_ACTIVE_DRAIN)
            else:
                player.stamina = max(0.0, player.stamina - STAMINA_IDLE_DRAIN)

        # ── Log tick events to S3 (fire and forget) ──────────────────────
        log_tasks = [
            log_tick_event(
                TickEvent(
                    tick=tick,
                    match_id=match_id,
                    timestamp=datetime.now(timezone.utc),
                    player_id=pid,
                    command=command,
                    latency_ms=latency_ms,
                    game_state_snapshot=game_state,
                )
            )
            for pid, (command, latency_ms) in agent_results.items()
        ]
        await asyncio.gather(*log_tasks, return_exceptions=True)

        # ── Broadcast to WebSocket clients ───────────────────────────────
        await broadcast_game_state(match_id, game_state)

        # ── Half time break ───────────────────────────────────────────────
        if tick == HALF_TIME_TICK - 1:
            game_state.phase = GamePhase.HALF_TIME
            await broadcast_game_state(match_id, game_state)
            logger.info(f"Match {match_id} — HALF TIME")
            await asyncio.sleep(HALF_TIME_BREAK_SECONDS)
            game_state.phase = GamePhase.SECOND_HALF

        # ── Precise 2s tick timing ────────────────────────────────────────
        elapsed = asyncio.get_event_loop().time() - tick_start
        sleep_time = max(0.0, TICK_INTERVAL_SECONDS - elapsed)
        if sleep_time < 0.05:
            logger.warning(f"Tick {tick} overran: elapsed={elapsed:.3f}s")
        await asyncio.sleep(sleep_time)

    # ── Full time ────────────────────────────────────────────────────────
    game_state.phase = GamePhase.FULL_TIME
    game_state.tick = MATCH_DURATION_TICKS
    game_state.clock_seconds = MATCH_DURATION_TICKS * 2

    await broadcast_game_state(match_id, game_state)
    await log_match_summary(match_id, game_state)

    winner = _determine_winner(game_state)
    logger.info(
        f"Match {match_id} FULL TIME | "
        f"Scores: {[(s.team_name, s.goals) for s in game_state.scores]} | "
        f"Winner: {winner}"
    )
    return game_state


def _reset_to_kickoff(game_state: GameState, scored_by: str) -> GameState:
    """Reset ball to centre. Restore players to kickoff formation."""
    game_state.ball.position = Position(x=0.0, y=0.0)
    game_state.ball.velocity = Velocity(vx=0.0, vy=0.0)
    game_state.ball.last_touched_by = None
    _reset_player_positions(game_state)
    return game_state


def _reset_player_positions(game_state: GameState) -> None:
    """Restore all players to their base kickoff positions."""
    for player in game_state.players:
        if player.player_id in BASE_POSITIONS:
            x, y = BASE_POSITIONS[player.player_id]
            player.position = Position(x=x, y=y)
            player.velocity = Velocity(vx=0.0, vy=0.0)
            player.has_ball = False


def _determine_winner(game_state: GameState) -> str:
    if len(game_state.scores) < 2:
        return "unknown"
    a, b = game_state.scores[0], game_state.scores[1]
    if a.goals > b.goals:
        return a.team_name
    if b.goals > a.goals:
        return b.team_name
    return "draw"


def build_initial_game_state(
    match_id: str,
    team_a_id: str,
    team_a_name: str,
    team_b_id: str,
    team_b_name: str,
) -> GameState:
    """
    Factory: build a fresh GameState ready for kickoff.
    Team A players use the standard BASE_POSITIONS.
    Team B players are mirrored (x negated) to start on opposite side.
    """
    from game_state import BallState, GameState, PlayerRole, TeamScore

    team_a_players = [
        PlayerState(
            player_id="GK_01",
            team_id=team_a_id,
            role=PlayerRole.GOALKEEPER,
            position=Position(x=-28.0, y=0.0),
        ),
        PlayerState(
            player_id="DEF_L",
            team_id=team_a_id,
            role=PlayerRole.DEFENDER,
            position=Position(x=-15.0, y=-7.0),
        ),
        PlayerState(
            player_id="DEF_R",
            team_id=team_a_id,
            role=PlayerRole.DEFENDER,
            position=Position(x=-15.0, y=7.0),
        ),
        PlayerState(
            player_id="MID_01",
            team_id=team_a_id,
            role=PlayerRole.MIDFIELDER,
            position=Position(x=0.0, y=0.0),
        ),
        PlayerState(
            player_id="STR_01",
            team_id=team_a_id,
            role=PlayerRole.STRIKER,
            position=Position(x=12.0, y=0.0),
        ),
    ]

    # Team B: mirrored positions, distinct player_ids
    team_b_players = [
        PlayerState(
            player_id="B_GK_01",
            team_id=team_b_id,
            role=PlayerRole.GOALKEEPER,
            position=Position(x=28.0, y=0.0),
        ),
        PlayerState(
            player_id="B_DEF_L",
            team_id=team_b_id,
            role=PlayerRole.DEFENDER,
            position=Position(x=15.0, y=-7.0),
        ),
        PlayerState(
            player_id="B_DEF_R",
            team_id=team_b_id,
            role=PlayerRole.DEFENDER,
            position=Position(x=15.0, y=7.0),
        ),
        PlayerState(
            player_id="B_MID_01",
            team_id=team_b_id,
            role=PlayerRole.MIDFIELDER,
            position=Position(x=0.0, y=2.0),
        ),
        PlayerState(
            player_id="B_STR_01",
            team_id=team_b_id,
            role=PlayerRole.STRIKER,
            position=Position(x=-12.0, y=0.0),
        ),
    ]

    return GameState(
        match_id=match_id,
        tick=0,
        clock_seconds=0,
        phase=GamePhase.PRE_MATCH,
        players=team_a_players + team_b_players,
        ball=BallState(position=Position(x=0.0, y=0.0)),
        scores=[
            TeamScore(team_id=team_a_id, team_name=team_a_name, goals=0),
            TeamScore(team_id=team_b_id, team_name=team_b_name, goals=0),
        ],
    )
