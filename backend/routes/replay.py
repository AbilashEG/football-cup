"""
Replay routes — serve match replay data for the frontend replay viewer.
Reads NDJSON event log and summary JSON from S3.
"""

import json
import logging
import os
from typing import Optional

import boto3
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/replay", tags=["replay"])

BUCKET_NAME = os.environ.get("BUCKET_NAME", "football-cup-events")
REGION = os.environ.get("AWS_REGION", "us-east-1")

s3 = boto3.client("s3", region_name=REGION)


# ── GET /replay/{match_id}/summary ───────────────────────────────────────────

@router.get("/{match_id}/summary")
async def get_replay_summary(match_id: str) -> dict:
    """Return the match summary JSON written at FULL_TIME."""
    s3_key = f"football-cup-events/{match_id}/summary.json"
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        raise HTTPException(
            status_code=404,
            detail=f"Summary not found for match {match_id}. Match may still be running.",
        )
    except Exception as e:
        logger.error(f"get_replay_summary error for {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /replay/{match_id}/stream ─────────────────────────────────────────────

@router.get("/{match_id}/stream")
async def stream_replay(match_id: str):
    """
    Stream the full NDJSON event log.
    Frontend replay viewer reads line-by-line with a configurable delay
    to animate the match at any speed.
    """
    s3_key = f"football-cup-events/{match_id}/events.ndjson"
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
    except s3.exceptions.NoSuchKey:
        raise HTTPException(
            status_code=404,
            detail=f"Replay not available for match {match_id}",
        )

    def _generator():
        for chunk in obj["Body"].iter_chunks(chunk_size=8192):
            yield chunk

    return StreamingResponse(
        _generator(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'inline; filename="replay_{match_id}.ndjson"',
            "Cache-Control": "no-cache",
        },
    )


# ── GET /replay/{match_id}/tick/{tick} ────────────────────────────────────────

@router.get("/{match_id}/tick/{tick}")
async def get_tick_snapshot(match_id: str, tick: int) -> dict:
    """
    Return all TickEvents for a specific tick number.
    Used by the frontend scrubber to jump to any point in the match.
    """
    s3_key = f"football-cup-events/{match_id}/events.ndjson"
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        raw = obj["Body"].read().decode("utf-8")
    except s3.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail=f"No events for match {match_id}")

    tick_events = []
    game_state_snapshot = None

    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        evt = json.loads(line)
        if evt.get("tick") == tick:
            tick_events.append(evt)
            if not game_state_snapshot:
                game_state_snapshot = evt.get("game_state_snapshot")

    if not tick_events:
        raise HTTPException(
            status_code=404,
            detail=f"No events found for tick {tick} in match {match_id}",
        )

    return {
        "match_id": match_id,
        "tick": tick,
        "events": tick_events,
        "game_state": game_state_snapshot,
        "commands": [
            {
                "player_id": e.get("player_id"),
                "command": e.get("command"),
                "latency_ms": e.get("latency_ms"),
            }
            for e in tick_events
        ],
    }


# ── GET /replay/{match_id}/player/{player_id} ─────────────────────────────────

@router.get("/{match_id}/player/{player_id}")
async def get_player_replay(
    match_id: str,
    player_id: str,
    from_tick: int = Query(default=0, ge=0),
    to_tick: int = Query(default=60, ge=0),
) -> dict:
    """
    Return all decisions made by a specific player in a tick range.
    Used by the StrategyTuner to show why an agent made certain choices.
    """
    s3_key = f"football-cup-events/{match_id}/events.ndjson"
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        raw = obj["Body"].read().decode("utf-8")
    except s3.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail=f"No events for match {match_id}")

    decisions = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        evt = json.loads(line)
        if (
            evt.get("player_id") == player_id
            and from_tick <= int(evt.get("tick", 0)) <= to_tick
        ):
            decisions.append(
                {
                    "tick": evt.get("tick"),
                    "command_type": evt.get("command", {}).get("type"),
                    "rationale": evt.get("command", {}).get("rationale"),
                    "latency_ms": evt.get("latency_ms"),
                    "target_player_id": evt.get("command", {}).get("target_player_id"),
                    "target_position": evt.get("command", {}).get("target_position"),
                }
            )

    return {
        "match_id": match_id,
        "player_id": player_id,
        "from_tick": from_tick,
        "to_tick": to_tick,
        "total_decisions": len(decisions),
        "decisions": decisions,
    }
