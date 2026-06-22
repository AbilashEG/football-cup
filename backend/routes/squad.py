"""
Squad routes — create, get, list, update squad configurations.
Squads are persisted in DynamoDB football-squads table.
"""

import json
import logging
import os
import uuid
from typing import Optional

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/squad", tags=["squad"])

TABLE_NAME = os.environ.get("SQUADS_TABLE_NAME", "football-squads")
REGION = os.environ.get("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)


class AgentConfig(BaseModel):
    player_id: str
    role: str  # GOALKEEPER | DEFENDER | MIDFIELDER | STRIKER
    system_prompt: str = Field(..., max_length=2000)
    agentcore_endpoint: Optional[str] = None


class SquadConfig(BaseModel):
    squad_name: str = Field(..., max_length=60)
    team_color: str = Field(default="#00D4FF", max_length=7)
    formation: str = Field(default="4-1", max_length=10)  # e.g. "4-1", "3-2", "2-2-1"
    agents: list[AgentConfig] = Field(..., min_length=5, max_length=5)
    owner_id: Optional[str] = None


class UpdateSquadRequest(BaseModel):
    squad_name: Optional[str] = Field(None, max_length=60)
    team_color: Optional[str] = Field(None, max_length=7)
    formation: Optional[str] = Field(None, max_length=10)
    agents: Optional[list[AgentConfig]] = None


# ── POST /squad ───────────────────────────────────────────────────────────────

@router.post("/")
async def create_squad(request: SquadConfig) -> dict:
    """Create a new squad configuration and persist to DynamoDB."""
    squad_id = str(uuid.uuid4())[:12].upper()

    item = {
        "squad_id": squad_id,
        "squad_name": request.squad_name,
        "team_color": request.team_color,
        "formation": request.formation,
        "agents": json.dumps([a.model_dump() for a in request.agents]),
        "owner_id": request.owner_id or "anonymous",
    }

    try:
        table.put_item(Item=item)
    except Exception as e:
        logger.error(f"create_squad DynamoDB error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save squad")

    logger.info(f"Squad created: {squad_id} — {request.squad_name}")
    return {"squad_id": squad_id, **request.model_dump()}


# ── GET /squad/{squad_id} ─────────────────────────────────────────────────────

@router.get("/{squad_id}")
async def get_squad(squad_id: str) -> dict:
    """Retrieve a squad by squad_id."""
    try:
        response = table.get_item(Key={"squad_id": squad_id})
    except Exception as e:
        logger.error(f"get_squad error: {e}")
        raise HTTPException(status_code=500, detail="DynamoDB error")

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail=f"Squad {squad_id} not found")

    return _deserialise_squad(item)


# ── GET /squad ────────────────────────────────────────────────────────────────

@router.get("/")
async def list_squads(owner_id: Optional[str] = None) -> dict:
    """
    List all squads. Optionally filter by owner_id.
    Uses a DynamoDB scan — acceptable for workshop scale (<100 squads).
    """
    try:
        if owner_id:
            response = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("owner_id").eq(owner_id)
            )
        else:
            response = table.scan()
    except Exception as e:
        logger.error(f"list_squads error: {e}")
        raise HTTPException(status_code=500, detail="DynamoDB error")

    squads = [_deserialise_squad(item) for item in response.get("Items", [])]
    return {"squads": squads, "count": len(squads)}


# ── PATCH /squad/{squad_id} ───────────────────────────────────────────────────

@router.patch("/{squad_id}")
async def update_squad(squad_id: str, request: UpdateSquadRequest) -> dict:
    """Update squad fields. Supports partial update."""
    # Check exists
    existing = table.get_item(Key={"squad_id": squad_id}).get("Item")
    if not existing:
        raise HTTPException(status_code=404, detail=f"Squad {squad_id} not found")

    update_expr_parts = []
    expr_values = {}

    if request.squad_name is not None:
        update_expr_parts.append("squad_name = :name")
        expr_values[":name"] = request.squad_name

    if request.team_color is not None:
        update_expr_parts.append("team_color = :color")
        expr_values[":color"] = request.team_color

    if request.formation is not None:
        update_expr_parts.append("formation = :formation")
        expr_values[":formation"] = request.formation

    if request.agents is not None:
        update_expr_parts.append("agents = :agents")
        expr_values[":agents"] = json.dumps([a.model_dump() for a in request.agents])

    if not update_expr_parts:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        table.update_item(
            Key={"squad_id": squad_id},
            UpdateExpression="SET " + ", ".join(update_expr_parts),
            ExpressionAttributeValues=expr_values,
        )
    except Exception as e:
        logger.error(f"update_squad error: {e}")
        raise HTTPException(status_code=500, detail="DynamoDB update failed")

    logger.info(f"Squad updated: {squad_id}")
    updated = table.get_item(Key={"squad_id": squad_id}).get("Item", {})
    return _deserialise_squad(updated)


# ── DELETE /squad/{squad_id} ──────────────────────────────────────────────────

@router.delete("/{squad_id}")
async def delete_squad(squad_id: str) -> dict:
    """Delete a squad configuration."""
    try:
        table.delete_item(Key={"squad_id": squad_id})
    except Exception as e:
        logger.error(f"delete_squad error: {e}")
        raise HTTPException(status_code=500, detail="DynamoDB error")

    logger.info(f"Squad deleted: {squad_id}")
    return {"squad_id": squad_id, "deleted": True}


# ── helpers ───────────────────────────────────────────────────────────────────

def _deserialise_squad(item: dict) -> dict:
    """Convert DynamoDB item back to squad dict with agents list parsed."""
    agents_raw = item.get("agents", "[]")
    if isinstance(agents_raw, str):
        agents = json.loads(agents_raw)
    else:
        agents = agents_raw

    return {
        "squad_id": item.get("squad_id"),
        "squad_name": item.get("squad_name"),
        "team_color": item.get("team_color", "#00D4FF"),
        "formation": item.get("formation", "4-1"),
        "owner_id": item.get("owner_id"),
        "agents": agents,
    }
