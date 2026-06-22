"""
AgentCore Runtime client — NEW ARCHITECTURE.

ONE coach endpoint receives the full GameState every tick.
Coach fans out to all 5 player Lambdas internally and returns
all 5 AgentCommands in a single response.

Old architecture (REMOVED): 5 separate endpoints, 5 parallel HTTP calls.
New architecture: 1 coach endpoint → returns {GK_01, DEF_L, DEF_R, MID_01, STR_01}.
"""

import asyncio
import json
import logging
import time

import aiohttp
import boto3

from command_schema import AgentCommand, CommandType
from game_state import GameState

logger = logging.getLogger(__name__)

HARD_TIMEOUT = 0.95       # 950ms — 50ms buffer inside 1s contract
PLAYER_IDS = ["GK_01", "DEF_L", "DEF_R", "MID_01", "STR_01"]

# Module-level cache — SSM read once on Lambda cold start
_coach_endpoint_cache: str = ""


def _load_coach_endpoint() -> str:
    """
    Load the single coach AgentCore endpoint from SSM.
    Stored by deploy.sh as /football-cup/coach/agentcore_endpoint.
    Cached at module scope — only hits SSM on cold start.
    """
    global _coach_endpoint_cache
    if _coach_endpoint_cache:
        return _coach_endpoint_cache

    try:
        ssm = boto3.client("ssm", region_name="us-east-1")
        param = ssm.get_parameter(
            Name="/football-cup/coach/agentcore_endpoint",
            WithDecryption=False,
        )
        _coach_endpoint_cache = param["Parameter"]["Value"]
        logger.info("Coach endpoint loaded: %s", _coach_endpoint_cache)
    except Exception as e:
        logger.error("Failed to load coach endpoint from SSM: %s", e)
        _coach_endpoint_cache = ""

    return _coach_endpoint_cache


def _idle_command(reason: str) -> AgentCommand:
    return AgentCommand(type=CommandType.IDLE, rationale=reason[:120])


def _all_idle(reason: str) -> dict[str, tuple[AgentCommand, float]]:
    """Return IDLE for all 5 players — used as a safe fallback."""
    cmd = _idle_command(reason)
    return {pid: (cmd, 0.0) for pid in PLAYER_IDS}


async def invoke_all_agents_parallel(
    game_state: GameState,
    match_session_id: str,
) -> dict[str, tuple[AgentCommand, float]]:
    """
    Send full GameState to the coach AgentCore Runtime.
    Coach internally invokes all 5 player Lambdas in parallel
    and returns all 5 AgentCommands in one response.

    Returns dict: player_id → (AgentCommand, latency_ms).
    Never raises — always returns IDLE per player on any failure.
    """
    endpoint = _load_coach_endpoint()
    if not endpoint:
        logger.error("Coach endpoint not configured — all players IDLE")
        return _all_idle("Coach endpoint not configured")

    payload = {
        "input": game_state.model_dump(mode="json"),
        "sessionId": match_session_id,
    }

    start = time.monotonic()

    try:
        connector = aiohttp.TCPConnector(limit=5, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                endpoint,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=HARD_TIMEOUT),
            ) as resp:
                latency_ms = (time.monotonic() - start) * 1000

                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("Coach HTTP %d: %s", resp.status, body[:120])
                    return _all_idle(f"Coach HTTP {resp.status}")

                data = await resp.json()

    except asyncio.TimeoutError:
        latency_ms = (time.monotonic() - start) * 1000
        logger.warning("Coach timeout at %.0fms — all IDLE", latency_ms)
        return _all_idle(f"Coach timeout {latency_ms:.0f}ms")

    except aiohttp.ClientError as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("Coach network error: %s", e)
        return _all_idle("Coach network error")

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("Coach unexpected error: %s", e, exc_info=True)
        return _all_idle("Coach error")

    # Parse the combined response: { "output": { "GK_01": {...}, "DEF_L": {...}, ... } }
    output = data.get("output", data)
    results: dict[str, tuple[AgentCommand, float]] = {}

    for pid in PLAYER_IDS:
        raw = output.get(pid)
        if raw and isinstance(raw, dict):
            try:
                cmd = AgentCommand(**raw)
                results[pid] = (cmd, latency_ms)
                logger.info(
                    "%s → %s | %.0fms | %s",
                    pid, cmd.type.value, latency_ms, cmd.rationale,
                )
            except Exception as e:
                logger.warning("Failed to parse command for %s: %s", pid, e)
                results[pid] = (_idle_command(f"Parse error: {pid}"), latency_ms)
        else:
            logger.warning("No command returned for %s — IDLE", pid)
            results[pid] = (_idle_command(f"Missing in response: {pid}"), latency_ms)

    return results
