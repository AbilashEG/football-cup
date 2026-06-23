"""
coach/agent.py
==============
Football Coach — AgentCore Runtime.
Matches proven RFP orchestrator pattern exactly.

✅ HTTPServer on 0.0.0.0:8080  (NOT FastAPI / uvicorn)
✅ GET /health  → {"status":"healthy"}
✅ POST /       → receive GameState, call 5 player tools, return commands
✅ from strands.models import BedrockModel
✅ MCPClient with StreamableHTTPTransport → AgentCore Gateway
✅ AGENTCORE_GATEWAY_URL from env var
✅ get_workload_access_token() using agentRuntimeArn
✅ NEVER calls Lambda directly via boto3
✅ CMD ["python", "agent.py"]  (enforced in Dockerfile)
✅ python:3.12-slim base image (enforced in Dockerfile)
"""

import json
import logging
import os
import sys
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler

import boto3
from strands import Agent
from strands.models import BedrockModel                    # ✅ correct import
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, "/app/shared")
from command_schema import AgentCommand, CommandType       # noqa: E402
from game_state import GameState                           # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("football-coach")

# ─── Config ───────────────────────────────────────────────────────────────────
REGION      = os.environ.get("AWS_REGION", "us-east-1")
GATEWAY_URL = os.environ.get("AGENTCORE_GATEWAY_URL", "")
PORT        = 8080

PLAYER_IDS = ["GK_01", "DEF_L", "DEF_R", "MID_01", "STR_01"]

IDLE_ALL = {
    pid: {"type": "IDLE", "target_player_id": None,
          "target_position": None, "rationale": "Coach timeout"}
    for pid in PLAYER_IDS
}


# ─── Workload access token ────────────────────────────────────────────────────

def get_workload_access_token() -> str:
    """
    Gets workload identity token for AgentCore Gateway auth.
    Same pattern used in RFP orchestrator — proven working.
    """
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        response = client.get_token(
            agentRuntimeArn=os.environ.get("AGENT_RUNTIME_ARN", "")
        )
        return response["accessToken"]
    except Exception as e:
        logger.warning("get_workload_access_token failed: %s", e)
        return ""


# ─── Strands Agent ────────────────────────────────────────────────────────────

coach = Agent(
    model=BedrockModel(
        model_id="amazon.nova-micro-v1:0",
        region_name=REGION,
    ),
    system_prompt="""
You are a football coach. Every tick you receive the full game state.

Call ALL 5 player tools via the MCP Gateway:
  player_gk    → goalkeeper
  player_def_l → left defender
  player_def_r → right defender
  player_mid   → midfielder
  player_str   → striker

Pass the full game_state JSON string to every tool.
Return all 5 decisions as a single JSON object keyed by player_id:
{
  "GK_01":  {"type": "...", "rationale": "..."},
  "DEF_L":  {"type": "...", "rationale": "..."},
  "DEF_R":  {"type": "...", "rationale": "..."},
  "MID_01": {"type": "...", "rationale": "..."},
  "STR_01": {"type": "...", "rationale": "..."}
}

You have 900ms. Call all 5 tools. Never skip a player. Return JSON only.
""",
)


# ─── Coach sync runner ────────────────────────────────────────────────────────

def run_coach_sync(game_state_json: str) -> dict:
    """
    Connect to AgentCore Gateway via MCPClient, load player tools,
    call all 5 via the Strands Agent, return parsed command dict.
    Never raises — returns IDLE_ALL on any failure.
    """
    if not GATEWAY_URL:
        logger.error("AGENTCORE_GATEWAY_URL not set")
        return IDLE_ALL

    try:
        token = get_workload_access_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        with MCPClient(
            lambda: streamablehttp_client(
                GATEWAY_URL,
                headers=headers,
            )
        ) as mcp:
            coach.tools = mcp.get_tools()

            result = coach(
                f"New game tick. Call all 5 player tools "
                f"with this game state: {game_state_json}"
            )

        # Parse agent result → dict of 5 AgentCommands
        text = str(result)
        try:
            # Agent may return the JSON inside a code block — extract it
            if "```" in text:
                text = text.split("```")[1].strip()
                if text.startswith("json"):
                    text = text[4:].strip()
            commands = json.loads(text)
            if isinstance(commands, dict) and len(commands) > 0:
                return commands
        except json.JSONDecodeError:
            logger.error("Coach result not valid JSON: %s", text[:300])

        return IDLE_ALL

    except Exception as e:
        logger.error("run_coach_sync error: %s", e, exc_info=True)
        return IDLE_ALL


# ─── HTTP handler ─────────────────────────────────────────────────────────────

class CoachHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        logger.info(fmt, *args)

    def do_GET(self):
        # AgentCore hits /health for startup + liveness probes
        if self.path in ("/health", "/ping"):
            self._respond(200, {
                "status": "healthy",
                "agent": "football-coach",
                "gateway": GATEWAY_URL or "NOT_SET",
            })
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        # AgentCore Runtime invocation endpoint
        if self.path in ("/", "/invocations"):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)

            try:
                body = json.loads(raw) if raw else {}
                # AgentCore wraps payload as {"input": ...}
                game_state_raw = body.get("input", body)
                game_state_json = json.dumps(game_state_raw)

                # Run coach with 950ms hard timeout
                commands = asyncio.get_event_loop().run_until_complete(
                    asyncio.wait_for(
                        asyncio.to_thread(run_coach_sync, game_state_json),
                        timeout=0.95,
                    )
                )
            except asyncio.TimeoutError:
                logger.error("Coach hard timeout — all IDLE")
                commands = IDLE_ALL
            except Exception as e:
                logger.error("POST / error: %s", e)
                commands = IDLE_ALL

            logger.info(
                "Tick: %s",
                {k: v.get("type") for k, v in commands.items()},
            )
            self._respond(200, {"output": commands})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Football coach ready on 0.0.0.0:%d", PORT)
    logger.info("Gateway URL : %s", GATEWAY_URL or "NOT SET ⚠")
    server = HTTPServer(("0.0.0.0", PORT), CoachHandler)
    server.serve_forever()
