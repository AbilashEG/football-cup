"""
Match routes — start, hint, state, stats, replay.
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Optional

import boto3
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from game_state import GameState
from match_logger import get_match_events
from tick_engine import build_initial_game_state, run_match

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/match", tags=["match"])

TABLE_NAME = os.environ.get("TABLE_NAME", "football-game-state")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "football-cup-events")
WS_ENDPOINT = os.environ.get("WS_ENDPOINT_URL", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

# In-memory match registry for this Lambda instance
# Lambda has 10 reserved concurrencies — one match per warm instance
_active_matches: dict[str, GameState] = {}


class TeamConfig(BaseModel):
    team_id: str
    team_name: str


class StartMatchRequest(BaseModel):
    team_a: TeamConfig
    team_b: TeamConfig


class HintRequest(BaseModel):
    hint: str = Field(..., max_length=200)


# ── POST /match/start ────────────────────────────────────────────────────────

@router.post("/start")
async def start_match(
    request: StartMatchRequest, background_tasks: BackgroundTasks
) -> dict:
    """
    Initialise a new match and launch the tick engine as a background task.
    Returns match_id and WebSocket URL for the frontend to connect.
    """
    match_id = str(uuid.uuid4())[:8].upper()

    game_state = build_initial_game_state(
        match_id=match_id,
        team_a_id=request.team_a.team_id,
        team_a_name=request.team_a.team_name,
        team_b_id=request.team_b.team_id,
        team_b_name=request.team_b.team_name,
    )

    # Persist initial state to DynamoDB
    _save_game_state(match_id, 0, game_state)
    _active_matches[match_id] = game_state

    # Launch match as a background task (non-blocking)
    background_tasks.add_task(_run_match_task, match_id, game_state)

    ws_url = f"{WS_ENDPOINT}?matchId={match_id}" if WS_ENDPOINT else ""

    logger.info(
        f"Match started: {match_id} | "
        f"{request.team_a.team_name} vs {request.team_b.team_name}"
    )

    return {
        "match_id": match_id,
        "status": "started",
        "ws_url": ws_url,
        "team_a": request.team_a.model_dump(),
        "team_b": request.team_b.model_dump(),
    }


async def _run_match_task(match_id: str, game_state: GameState) -> None:
    """Background task wrapper for run_match — catches and logs any exception."""
    try:
        final_state = await run_match(match_id, game_state)
        _active_matches[match_id] = final_state
        _save_game_state(match_id, final_state.tick, final_state)
    except Exception as e:
        logger.error(f"Match {match_id} crashed: {e}", exc_info=True)


# ── POST /match/{match_id}/hint ──────────────────────────────────────────────

@router.post("/{match_id}/hint")
async def post_hint(match_id: str, request: HintRequest) -> dict:
    """
    Inject a coach hint into the live game state.
    The tick engine reads game_state.human_hint on the next tick.
    """
    game_state = _active_matches.get(match_id)
    if not game_state:
        # Try loading from DynamoDB (cross-instance scenario)
        game_state = _load_latest_game_state(match_id)
        if not game_state:
            raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    game_state.human_hint = request.hint[:200]

    # Also persist the hint to DynamoDB so the running Lambda instance picks it up
    try:
        table.update_item(
            Key={"match_id": match_id, "tick": -1},
            UpdateExpression="SET human_hint = :hint",
            ExpressionAttributeValues={":hint": request.hint[:200]},
        )
    except Exception as e:
        logger.warning(f"DynamoDB hint update failed (non-critical): {e}")

    logger.info(f"Coach hint set for {match_id}: '{request.hint[:60]}'")
    return {"match_id": match_id, "hint_accepted": True, "hint": request.hint[:200]}


# ── GET /match/{match_id}/state ──────────────────────────────────────────────

@router.get("/{match_id}/state")
async def get_match_state(match_id: str) -> dict:
    """Return the latest GameState for a match."""
    # Prefer in-memory (same Lambda instance)
    game_state = _active_matches.get(match_id)
    if game_state:
        return game_state.model_dump(mode="json")

    # Fall back to DynamoDB
    game_state = _load_latest_game_state(match_id)
    if not game_state:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    return game_state.model_dump(mode="json")


# ── GET /match/{match_id}/stats ──────────────────────────────────────────────

@router.get("/{match_id}/stats")
async def get_match_stats(match_id: str) -> dict:
    """
    Compute match statistics from the S3 NDJSON event log.
    Returns: possession_pct, shots, passes, tackles, goals_per_player.
    """
    events = await get_match_events(match_id)
    if not events:
        raise HTTPException(
            status_code=404,
            detail=f"No events found for match {match_id}",
        )

    stats: dict = {
        "match_id": match_id,
        "total_ticks": 0,
        "possession": {},
        "shots": {},
        "passes": {},
        "tackles": {},
        "goals": {},
        "command_counts": {},
        "avg_latency_ms": {},
        "timeouts": {},
    }

    latency_totals: dict[str, float] = {}
    latency_counts: dict[str, int] = {}
    max_tick = 0

    for evt in events:
        pid = evt.get("player_id", "unknown")
        cmd = evt.get("command", {})
        cmd_type = cmd.get("type", "IDLE")
        latency = float(evt.get("latency_ms", 0))
        tick = int(evt.get("tick", 0))
        max_tick = max(max_tick, tick)

        # Command counts
        if pid not in stats["command_counts"]:
            stats["command_counts"][pid] = {}
        stats["command_counts"][pid][cmd_type] = (
            stats["command_counts"][pid].get(cmd_type, 0) + 1
        )

        # Shots
        if cmd_type == "SHOOT":
            stats["shots"][pid] = stats["shots"].get(pid, 0) + 1

        # Passes
        if cmd_type == "PASS":
            stats["passes"][pid] = stats["passes"].get(pid, 0) + 1

        # Tackles
        if cmd_type == "TACKLE":
            stats["tackles"][pid] = stats["tackles"].get(pid, 0) + 1

        # Timeouts (IDLE from timeout)
        rationale = cmd.get("rationale", "")
        if "Timeout" in rationale or "timeout" in rationale:
            stats["timeouts"][pid] = stats["timeouts"].get(pid, 0) + 1

        # Latency tracking
        latency_totals[pid] = latency_totals.get(pid, 0.0) + latency
        latency_counts[pid] = latency_counts.get(pid, 0) + 1

        # Possession: ticks where player has ball
        snap = evt.get("game_state_snapshot", {})
        ball = snap.get("ball", {})
        if ball.get("last_touched_by") == pid:
            stats["possession"][pid] = stats["possession"].get(pid, 0) + 1

    stats["total_ticks"] = max_tick

    # Average latency per player
    for pid, total in latency_totals.items():
        count = latency_counts.get(pid, 1)
        stats["avg_latency_ms"][pid] = round(total / count, 1)

    # Possession percentage
    total_possession = sum(stats["possession"].values()) or 1
    stats["possession_pct"] = {
        pid: round(v / total_possession * 100, 1)
        for pid, v in stats["possession"].items()
    }

    return stats


# ── GET /match/{match_id}/replay ─────────────────────────────────────────────

@router.get("/{match_id}/replay")
async def get_match_replay(match_id: str):
    """
    Stream the full NDJSON event log from S3 as a StreamingResponse.
    The frontend replay viewer reads this line-by-line to reconstruct the match.
    """
    s3_key = f"football-cup-events/{match_id}/events.ndjson"
    s3_client = boto3.client("s3", region_name=REGION)

    try:
        obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(
            status_code=404,
            detail=f"Replay not available for match {match_id}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    def _stream():
        for chunk in obj["Body"].iter_chunks(chunk_size=4096):
            yield chunk

    return StreamingResponse(
        _stream(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="match_{match_id}_replay.ndjson"'
        },
    )


# ── GET /match/list ───────────────────────────────────────────────────────────

@router.get("/list")
async def list_matches() -> dict:
    """List all active in-memory matches on this Lambda instance."""
    return {
        "active_matches": [
            {
                "match_id": mid,
                "phase": gs.phase.value,
                "tick": gs.tick,
                "scores": [
                    {"team": s.team_name, "goals": s.goals}
                    for s in gs.scores
                ],
            }
            for mid, gs in _active_matches.items()
        ]
    }


# ── helpers ──────────────────────────────────────────────────────────────────

def _save_game_state(match_id: str, tick: int, game_state: GameState) -> None:
    try:
        import time
        table.put_item(
            Item={
                "match_id": match_id,
                "tick": tick,
                "game_state_json": json.dumps(
                    game_state.model_dump(mode="json"), default=str
                ),
                "phase": game_state.phase.value,
                "expires_at": int(time.time()) + (7 * 24 * 60 * 60),
            }
        )
    except Exception as e:
        logger.warning(f"_save_game_state error (non-critical): {e}")


def _load_latest_game_state(match_id: str) -> Optional[GameState]:
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("match_id").eq(
                match_id
            ),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return None
        return GameState(**json.loads(items[0]["game_state_json"]))
    except Exception as e:
        logger.error(f"_load_latest_game_state error: {e}")
        return None
