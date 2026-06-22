"""
Match event logger — writes TickEvent NDJSON lines to S3.
Also writes match summary JSON at FULL_TIME.
Matches the S3 write pattern from the Supplier RFP Management reference system.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

from game_state import GameState, TickEvent

logger = logging.getLogger(__name__)

BUCKET_NAME = os.environ.get("BUCKET_NAME", "football-cup-events")
s3 = boto3.client("s3", region_name="us-east-1")

# In-memory tick buffer — flushed to S3 in batches every N ticks
# Reduces S3 PUT calls from 5/tick to 1/tick
_tick_buffer: dict[str, list[str]] = {}   # match_id → list of NDJSON lines
FLUSH_EVERY_N_TICKS = 5                   # Flush buffer every 5 ticks (10s)
_last_flush_tick: dict[str, int] = {}


async def log_tick_event(tick_event: TickEvent) -> None:
    """
    Buffer TickEvent and flush to S3 every FLUSH_EVERY_N_TICKS ticks.
    Each line is a JSON-serialised TickEvent appended to:
      s3://{BUCKET}/football-cup-events/{match_id}/events.ndjson
    """
    match_id = tick_event.match_id
    tick = tick_event.tick

    line = json.dumps(tick_event.model_dump(mode="json"), default=str)

    if match_id not in _tick_buffer:
        _tick_buffer[match_id] = []
        _last_flush_tick[match_id] = -1

    _tick_buffer[match_id].append(line)

    # Flush on every FLUSH_EVERY_N_TICKS tick boundary, or on final tick
    should_flush = (
        tick % FLUSH_EVERY_N_TICKS == 0
        and tick != _last_flush_tick.get(match_id, -1)
    )

    if should_flush:
        await _flush_buffer(match_id, tick)


async def _flush_buffer(match_id: str, current_tick: int) -> None:
    """Append buffered lines to the NDJSON file in S3."""
    lines = _tick_buffer.get(match_id, [])
    if not lines:
        return

    s3_key = f"football-cup-events/{match_id}/events.ndjson"
    new_content = "\n".join(lines) + "\n"

    try:
        # Read existing content (S3 has no native append)
        existing = ""
        try:
            obj = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
            existing = obj["Body"].read().decode("utf-8")
        except s3.exceptions.NoSuchKey:
            pass

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=(existing + new_content).encode("utf-8"),
            ContentType="application/x-ndjson",
        )

        logger.info(
            f"match_logger: flushed {len(lines)} events for {match_id} "
            f"tick={current_tick} s3_key={s3_key}"
        )

        _tick_buffer[match_id] = []
        _last_flush_tick[match_id] = current_tick

    except Exception as e:
        logger.error(f"match_logger flush error for {match_id}: {e}", exc_info=True)
        # Do not clear buffer on error — retry on next flush


async def log_match_summary(match_id: str, game_state: GameState) -> None:
    """
    Write a match summary JSON to:
      s3://{BUCKET}/football-cup-events/{match_id}/summary.json

    Also force-flush any remaining buffered events.
    """
    # Final flush of remaining buffer
    if _tick_buffer.get(match_id):
        await _flush_buffer(match_id, game_state.tick)

    summary = _build_summary(match_id, game_state)
    s3_key = f"football-cup-events/{match_id}/summary.json"

    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=json.dumps(summary, default=str, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info(f"match_logger: summary written to {s3_key}")
    except Exception as e:
        logger.error(f"match_logger summary error for {match_id}: {e}", exc_info=True)


def _build_summary(match_id: str, game_state: GameState) -> dict[str, Any]:
    scores = [
        {"team_id": s.team_id, "team_name": s.team_name, "goals": s.goals}
        for s in game_state.scores
    ]

    if len(game_state.scores) >= 2:
        a, b = game_state.scores[0], game_state.scores[1]
        if a.goals > b.goals:
            winner = a.team_name
        elif b.goals > a.goals:
            winner = b.team_name
        else:
            winner = "draw"
    else:
        winner = "unknown"

    return {
        "match_id": match_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "total_ticks": game_state.tick,
        "duration_seconds": game_state.clock_seconds,
        "phase": game_state.phase.value,
        "scores": scores,
        "winner": winner,
        "players": [
            {
                "player_id": p.player_id,
                "team_id": p.team_id,
                "role": p.role.value,
                "final_stamina": round(p.stamina, 1),
                "final_position": {"x": p.position.x, "y": p.position.y},
            }
            for p in game_state.players
        ],
    }


async def get_match_events(match_id: str) -> list[dict]:
    """
    Read the full NDJSON event log from S3 and return as list of dicts.
    Used by replay and stats routes.
    """
    s3_key = f"football-cup-events/{match_id}/events.ndjson"
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        raw = obj["Body"].read().decode("utf-8")
        return [
            json.loads(line)
            for line in raw.strip().splitlines()
            if line.strip()
        ]
    except s3.exceptions.NoSuchKey:
        return []
    except Exception as e:
        logger.error(f"get_match_events error for {match_id}: {e}")
        return []
