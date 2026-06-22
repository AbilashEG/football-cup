"""
Shared Pydantic v2 AgentCommand schema.
Used by all 5 AgentCore Runtime agents and the FastAPI tick engine.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum


class CommandType(str, Enum):
    MOVE_TO = "MOVE_TO"
    PASS = "PASS"
    SHOOT = "SHOOT"
    DRIBBLE = "DRIBBLE"
    PRESS_BALL = "PRESS_BALL"
    MARK = "MARK"
    INTERCEPT = "INTERCEPT"
    TACKLE = "TACKLE"
    CLEAR = "CLEAR"
    IDLE = "IDLE"
    GOALKEEPER_DIVE = "GOALKEEPER_DIVE"


class Position(BaseModel):
    x: float = Field(..., ge=-30.0, le=30.0)
    y: float = Field(..., ge=-20.0, le=20.0)


class AgentCommand(BaseModel):
    type: CommandType
    target_player_id: Optional[str] = None
    target_position: Optional[Position] = None
    rationale: str = Field(
        ...,
        max_length=120,
        description="One short line. Appears in replay log and Agent Decision Feed UI.",
    )
