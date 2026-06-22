"""
2D physics simulation for the football pitch.
Translates AgentCommand → position deltas each tick.

Pitch boundaries: x ∈ [-30, 30], y ∈ [-20, 20]
Goals: left goal  x ≤ -29, |y| ≤ 4
       right goal x ≥  29, |y| ≤ 4
"""

import math
import random

from game_state import (
    AgentCommand,
    BallState,
    CommandType,
    GameState,
    PlayerState,
    Position,
    Velocity,
)

# Movement constants
PLAYER_SPEED = 3.0        # units per tick (MOVE_TO)
SPRINT_SPEED = 4.5        # units per tick (PRESS_BALL)
DRIBBLE_SPEED = 2.4       # units per tick (DRIBBLE — slower)
GK_DIVE_SPEED = 6.75      # units per tick (GOALKEEPER_DIVE — 1.5× sprint)

# Ball constants
BALL_PASS_SPEED = 8.0
BALL_SHOOT_SPEED = 14.0
BALL_CLEAR_SPEED = 11.0
BALL_FRICTION = 0.82      # velocity multiplier per tick

# Contact ranges
BALL_TOUCH_RANGE = 1.2    # player auto-captures ball within this distance
TACKLE_RANGE = 2.5        # maximum distance for tackle attempt
TACKLE_SUCCESS_RATE = 0.55
INTERCEPT_RANGE = 1.5     # distance at which INTERCEPT captures ball

# Pitch limits
PITCH_X_MIN, PITCH_X_MAX = -30.0, 30.0
PITCH_Y_MIN, PITCH_Y_MAX = -20.0, 20.0

# Goal geometry
GOAL_X_LEFT = -29.0
GOAL_X_RIGHT = 29.0
GOAL_HALF_WIDTH = 4.0


def apply_commands(
    game_state: GameState,
    agent_results: dict[str, tuple],  # player_id → (AgentCommand, latency_ms)
) -> GameState:
    """Apply all agent commands to the game state. Mutates in place and returns."""
    for player in game_state.players:
        result = agent_results.get(player.player_id)
        if not result:
            continue
        command, _ = result
        if player.is_active:
            _apply_single_command(game_state, player, command)
    return game_state


def _apply_single_command(
    game_state: GameState, player: PlayerState, command: AgentCommand
) -> None:
    ball = game_state.ball
    cmd_type = command.type

    if cmd_type == CommandType.MOVE_TO:
        if command.target_position:
            _move_player_toward(player, command.target_position, PLAYER_SPEED)

    elif cmd_type == CommandType.PRESS_BALL:
        _move_player_toward(player, ball.position, SPRINT_SPEED)
        # Auto-capture if close enough after sprint
        if _distance(player.position, ball.position) < BALL_TOUCH_RANGE:
            _capture_ball(player, ball)

    elif cmd_type == CommandType.PASS:
        if player.has_ball and command.target_player_id:
            target = _find_player(game_state, command.target_player_id)
            if target:
                _kick_ball_toward(ball, target.position, BALL_PASS_SPEED)
                player.has_ball = False
                ball.last_touched_by = player.player_id

    elif cmd_type == CommandType.SHOOT:
        if player.has_ball:
            # Aim at target_position if given, else right goal centre
            aim = command.target_position or Position(x=GOAL_X_RIGHT, y=0.0)
            _kick_ball_toward(ball, aim, BALL_SHOOT_SPEED)
            player.has_ball = False
            ball.last_touched_by = player.player_id

    elif cmd_type == CommandType.DRIBBLE:
        if player.has_ball and command.target_position:
            _move_player_toward(player, command.target_position, DRIBBLE_SPEED)
            # Ball follows player while dribbling
            ball.position = Position(x=player.position.x, y=player.position.y)
            ball.velocity = Velocity(vx=0.0, vy=0.0)

    elif cmd_type == CommandType.TACKLE:
        target = (
            _find_player(game_state, command.target_player_id)
            if command.target_player_id
            else _nearest_ball_carrier(game_state, player)
        )
        if target and _distance(player.position, target.position) < TACKLE_RANGE:
            if random.random() < TACKLE_SUCCESS_RATE:
                target.has_ball = False
                _capture_ball(player, ball)
            else:
                # Failed tackle — slight stamina penalty, player doesn't move
                player.stamina = max(0.0, player.stamina - 2.0)

    elif cmd_type == CommandType.CLEAR:
        in_range = (
            player.has_ball
            or _distance(player.position, ball.position) < BALL_TOUCH_RANGE + 0.5
        )
        if in_range:
            # Clear randomly to midfield flank
            clear_target = Position(
                x=0.0, y=random.uniform(-10.0, 10.0)
            )
            _kick_ball_toward(ball, clear_target, BALL_CLEAR_SPEED)
            player.has_ball = False
            ball.last_touched_by = player.player_id

    elif cmd_type == CommandType.GOALKEEPER_DIVE:
        _move_player_toward(player, ball.position, GK_DIVE_SPEED)
        if _distance(player.position, ball.position) < BALL_TOUCH_RANGE + 1.0:
            _capture_ball(player, ball)

    elif cmd_type == CommandType.MARK:
        if command.target_player_id:
            target = _find_player(game_state, command.target_player_id)
            if target:
                # Position 1.5 units goal-side of the marked player
                mark_pos = Position(
                    x=_clamp(target.position.x - 1.5, PITCH_X_MIN, PITCH_X_MAX),
                    y=_clamp(target.position.y, PITCH_Y_MIN, PITCH_Y_MAX),
                )
                _move_player_toward(player, mark_pos, PLAYER_SPEED)

    elif cmd_type == CommandType.INTERCEPT:
        if command.target_position:
            _move_player_toward(player, command.target_position, PLAYER_SPEED)
        if _distance(player.position, ball.position) < INTERCEPT_RANGE:
            _capture_ball(player, ball)

    # IDLE: no position update


def update_ball_physics(game_state: GameState) -> GameState:
    """
    Apply friction and boundary clamping to ball each tick.
    Check if any player is now within touch range to auto-capture.
    """
    ball = game_state.ball

    # Advance position
    new_x = _clamp(ball.position.x + ball.velocity.vx, PITCH_X_MIN, PITCH_X_MAX)
    new_y = _clamp(ball.position.y + ball.velocity.vy, PITCH_Y_MIN, PITCH_Y_MAX)

    # Bounce off side lines (y boundaries)
    if ball.position.y + ball.velocity.vy > PITCH_Y_MAX or \
       ball.position.y + ball.velocity.vy < PITCH_Y_MIN:
        ball.velocity.vy *= -0.5

    ball.position = Position(x=new_x, y=new_y)

    # Apply friction
    ball.velocity.vx *= BALL_FRICTION
    ball.velocity.vy *= BALL_FRICTION

    # Stop near-stationary ball
    if abs(ball.velocity.vx) < 0.05:
        ball.velocity.vx = 0.0
    if abs(ball.velocity.vy) < 0.05:
        ball.velocity.vy = 0.0

    # Auto-capture: first player within touch range picks up loose ball
    loose = not any(p.has_ball for p in game_state.players)
    if loose:
        for player in sorted(
            game_state.players,
            key=lambda p: _distance(p.position, ball.position),
        ):
            if player.is_active and _distance(player.position, ball.position) < BALL_TOUCH_RANGE:
                _capture_ball(player, ball)
                break

    return game_state


def detect_goal(game_state: GameState) -> str | None:
    """
    Returns the team_id of the scoring team if a goal is detected, else None.
    Right goal (x ≥ 29) → team owning left side scores (scores[0]).
    Left goal  (x ≤ -29) → team owning right side scores (scores[1]).
    """
    ball = game_state.ball

    if ball.position.x >= GOAL_X_RIGHT and abs(ball.position.y) <= GOAL_HALF_WIDTH:
        if len(game_state.scores) > 0:
            return game_state.scores[0].team_id

    if ball.position.x <= GOAL_X_LEFT and abs(ball.position.y) <= GOAL_HALF_WIDTH:
        if len(game_state.scores) > 1:
            return game_state.scores[1].team_id

    return None


# ── helpers ─────────────────────────────────────────────────────────────────

def _move_player_toward(player: PlayerState, target: Position, speed: float) -> None:
    dx = target.x - player.position.x
    dy = target.y - player.position.y
    dist = math.sqrt(dx * dx + dy * dy)
    if dist > 0.1:
        step = min(speed, dist)
        player.position = Position(
            x=_clamp(player.position.x + (dx / dist) * step, PITCH_X_MIN, PITCH_X_MAX),
            y=_clamp(player.position.y + (dy / dist) * step, PITCH_Y_MIN, PITCH_Y_MAX),
        )
        # Update velocity for momentum tracking
        player.velocity = Velocity(
            vx=(dx / dist) * step,
            vy=(dy / dist) * step,
        )


def _kick_ball_toward(ball: BallState, target: Position, speed: float) -> None:
    dx = target.x - ball.position.x
    dy = target.y - ball.position.y
    dist = math.sqrt(dx * dx + dy * dy)
    if dist > 0:
        ball.velocity = Velocity(
            vx=(dx / dist) * speed,
            vy=(dy / dist) * speed,
        )


def _capture_ball(player: PlayerState, ball: BallState) -> None:
    """Player captures ball — all other players lose possession."""
    player.has_ball = True
    ball.velocity = Velocity(vx=0.0, vy=0.0)
    ball.last_touched_by = player.player_id


def _find_player(game_state: GameState, player_id: str) -> PlayerState | None:
    return next((p for p in game_state.players if p.player_id == player_id), None)


def _nearest_ball_carrier(
    game_state: GameState, me: PlayerState
) -> PlayerState | None:
    """Find nearest opponent carrying the ball."""
    carriers = [
        p
        for p in game_state.players
        if p.has_ball and p.team_id != me.team_id
    ]
    if not carriers:
        return None
    return min(carriers, key=lambda p: _distance(me.position, p.position))


def _distance(a: Position, b: Position) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
