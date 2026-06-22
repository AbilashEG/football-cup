"""
Shared Pydantic v2 GameState models.
Used by all agents, tick engine, and MCP tools.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime

from command_schema import AgentCommand, Position


class PlayerRole(str, Enum):
    GOALKEEPER = "GOALKEEPER"
    DEFENDER = "DEFENDER"
    MIDFIELDER = "MIDFIELDER"
    STRIKER = "STRIKER"


class GamePhase(str, Enum):
    PRE_MATCH = "PRE_MATCH"
    FIRST_HALF = "FIRST_HALF"
    HALF_TIME = "HALF_TIME"
    SECOND_HALF = "SECOND_HALF"
    FULL_TIME = "FULL_TIME"


class Velocity(BaseModel):
    vx: float = Field(default=0.0)
    vy: float = Field(default=0.0)


class PlayerState(BaseModel):
    player_id: str
    team_id: str
    role: PlayerRole
    position: Position
    velocity: Velocity = Field(default_factory=Velocity)
    stamina: float = Field(default=100.0, ge=0.0, le=100.0)
    has_ball: bool = False
    is_active: bool = True


class BallState(BaseModel):
    position: Position
    velocity: Velocity = Field(default_factory=Velocity)
    last_touched_by: Optional[str] = None


class TeamScore(BaseModel):
    team_id: str
    team_name: str
    goals: int = 0


class GameState(BaseModel):
    match_id: str
    tick: int = Field(default=0, ge=0)
    clock_seconds: int = Field(default=0, ge=0)
    phase: GamePhase = GamePhase.PRE_MATCH
    players: list[PlayerState] = Field(default_factory=list)
    ball: BallState = Field(
        default_factory=lambda: BallState(position=Position(x=0.0, y=0.0))
    )
    scores: list[TeamScore] = Field(default_factory=list)
    human_hint: Optional[str] = Field(default=None, max_length=200)


class TickEvent(BaseModel):
    tick: int
    match_id: str
    timestamp: datetime
    player_id: str
    command: AgentCommand
    latency_ms: float
    game_state_snapshot: GameState
