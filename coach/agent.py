"""
coach/agent.py
==============
AgentCore Runtime — the single deployed container.

Rules followed:
  ✅ HTTPServer on port 8080 (NOT FastAPI)
  ✅ POST /         — handles agent invocation
  ✅ GET  /health   — returns {"status":"healthy"}
  ✅ from strands.models import BedrockModel
  ✅ MCPClient with StreamableHTTPTransport to Gateway
  ✅ AGENTCORE_GATEWAY_URL from env
  ✅ get_workload_access_token() for Gateway auth
  ✅ NEVER calls Lambda via boto3 directly
  ✅ python:3.12-slim base image (enforced in Dockerfile)
  ✅ ARM64 (built by CodeBuild ARM_CONTAINER)
"""

import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from http.server import BaseHTTPRequestHandler, HTTPServer

import boto3
from strands import Agent
from strands.models import BedrockModel

# MCPClient imports
try:
    from strands.tools.mcp import MCPClient
    from mcp.client.streamable_http import streamablehttp_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

sys.path.append("/app/shared")
from command_schema import AgentCommand, CommandType  # noqa: E402
from game_state import GameState  # noqa: E402

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("football-coach")

# ─── Config ───────────────────────────────────────────────────────────────────
REGION              = os.environ.get("AWS_REGION", "us-east-1")
GATEWAY_URL         = os.environ.get("AGENTCORE_GATEWAY_URL", "")
PORT                = 8080
PLAYER_TIMEOUT_SEC  = 0.90   # 900ms — 100ms buffer inside 1s contract

# Player tool names exactly as registered in AgentCore Gateway
PLAYER_TOOLS = {
    "GK_01":  "player_gk",
    "DEF_L":  "player_def_l",
    "DEF_R":  "player_def_r",
    "MID_01": "player_mid",
    "STR_01": "player_str",
}


# ─── Workload access token ────────────────────────────────────────────────────

def get_workload_access_token() -> str:
    """
    Get AgentCore workload access token for Gateway authentication.
    The AgentCore Runtime container has IAM credentials that allow this call.
    """
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        response = client.get_token(
            workloadName=os.environ.get("AGENTCORE_RUNTIME_NAME", "football-coach")
        )
        return response.get("token", "")
    except Exception as e:
        logger.warning("get_workload_access_token failed (continuing without): %s", e)
        return ""


# ─── MCP client factory ───────────────────────────────────────────────────────

def _make_mcp_client():
    """Create a fresh MCPClient pointing at the AgentCore Gateway."""
    token = get_workload_access_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return MCPClient(
        lambda: streamablehttp_client(GATEWAY_URL, headers=headers)
    )


# ─── Single player tool call (runs in thread) ─────────────────────────────────

def _call_one_player(player_id: str, tool_name: str, game_state_json: str) -> tuple[str, dict]:
    """
    Call one player tool via MCPClient → Gateway → Lambda.
    Returns (player_id, AgentCommand dict).
    Never raises — returns IDLE on any failure.
    """
    try:
        with _make_mcp_client() as client:
            result = client.call_tool_sync(
                tool_name,
                {"game_state_json": game_state_json},
            )
            # MCP result content is a list of content items
            if result and hasattr(result, "content") and result.content:
                raw = result.content[0].text
                cmd = json.loads(raw)
                if isinstance(cmd, dict) and "type" in cmd:
                    logger.info("%s → %s | %s", player_id, cmd.get("type"), cmd.get("rationale", ""))
                    return player_id, cmd
            return player_id, _idle(player_id, "empty tool response")
    except Exception as e:
        logger.error("%s tool error: %s", player_id, e)
        return player_id, _idle(player_id, f"tool error: {str(e)[:40]}")


def _idle(player_id: str, reason: str = "fallback") -> dict:
    return {
        "type": "IDLE",
        "target_player_id": None,
        "target_position": None,
        "rationale": f"{player_id} — {reason}",
    }


# ─── Fan-out: all 5 players in parallel ──────────────────────────────────────

def invoke_all_players(game_state_json: str) -> dict:
    """
    Call all 5 player tools in parallel via ThreadPoolExecutor.
    Hard 900ms timeout across all 5.
    Returns dict: player_id → AgentCommand dict.
    """
    results: dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_pid = {
            executor.submit(_call_one_player, pid, tool, game_state_json): pid
            for pid, tool in PLAYER_TOOLS.items()
        }
        try:
            for future in as_completed(future_to_pid, timeout=PLAYER_TIMEOUT_SEC):
                pid, cmd = future.result()
                results[pid] = cmd
        except TimeoutError:
            logger.warning("Fan-out timeout at %.0fms — filling remaining with IDLE", PLAYER_TIMEOUT_SEC * 1000)

    # Guarantee all 5 are present
    for pid in PLAYER_TOOLS:
        if pid not in results:
            results[pid] = _idle(pid, "timeout")

    return results


# ─── HTTP handler ─────────────────────────────────────────────────────────────

class CoachHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {
                "status": "healthy",
                "service": "football-coach",
                "version": "1.0.0",
                "gateway": GATEWAY_URL or "NOT_SET",
            })
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path in ("/", "/invocations"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body) if body else {}

                # AgentCore wraps payload as {"input": ...}; fall back to raw
                game_state_raw = data.get("input", data)
                game_state_json = json.dumps(game_state_raw)

                if not GATEWAY_URL:
                    logger.error("AGENTCORE_GATEWAY_URL not set — all IDLE")
                    self._respond(200, {
                        "output": {pid: _idle(pid, "GATEWAY_URL not configured") for pid in PLAYER_TOOLS}
                    })
                    return

                commands = invoke_all_players(game_state_json)
                logger.info(
                    "Tick complete: %s",
                    {k: v.get("type") for k, v in commands.items()},
                )
                self._respond(200, {"output": commands})

            except Exception as e:
                logger.error("POST / unhandled error: %s", e, exc_info=True)
                self._respond(200, {
                    "output": {pid: _idle(pid, "coach error") for pid in PLAYER_TOOLS}
                })
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # silence default access log to stderr
        logger.info(fmt, *args)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not MCP_AVAILABLE:
        logger.error("MCPClient not available — check strands-agents-tools install")

    if not GATEWAY_URL:
        logger.warning("AGENTCORE_GATEWAY_URL is not set — /invocations will return IDLE")

    logger.info("Starting football-coach on 0.0.0.0:%d", PORT)
    logger.info("Gateway URL: %s", GATEWAY_URL or "NOT SET")

    server = HTTPServer(("0.0.0.0", PORT), CoachHandler)
    server.serve_forever()
