# AWS Agentic Football Cup

5v5 autonomous football with **Strands Agents SDK** on **Amazon Bedrock AgentCore Runtime**.  
Each player is an independent AI agent that receives game state every 2 seconds and returns a structured command within 1 second.

---

## Architecture

```
┌─────────────────────────────┐
│     Next.js 14 Frontend     │  Amplify / localhost:3000
└────────────┬────────────────┘
             │ HTTPS + WebSocket
┌────────────▼────────────────┐
│    API Gateway HTTP + WS    │  us-east-1
└────────────┬────────────────┘
             │
┌────────────▼────────────────┐
│   FastAPI Lambda (Mangum)   │  ARM64 · 1024MB · 30s
│   Tick Engine + Match Mgr   │
└────────────┬────────────────┘
             │ asyncio.gather (parallel)
    ┌────────┴──────────┐
    │                   │
┌───▼────────┐  ┌───────▼────────┐
│ AgentCore  │  │  AgentCore     │  × 5 agents
│ Runtime    │  │  Runtime       │  ARM64 · port 8080
│ /invocations│  │ /invocations  │  950ms hard timeout
└───┬────────┘  └───────┬────────┘
    │                   │
    └────────┬──────────┘
             │
    ┌────────▼──────────┐
    │  amazon.nova-     │
    │  micro-v1:0       │  us-east-1
    └───────────────────┘
             │
    ┌────────▼──────────┐   ┌────────────────┐
    │  Lambda MCP ×6    │   │   DynamoDB     │
    │  ARM64 256MB 10s  │   │   + S3 NDJSON  │
    └───────────────────┘   └────────────────┘
```

### Key design decisions

| Decision | Rationale |
|---|---|
| `amazon.nova-micro-v1:0` | Fits 1-second latency budget. Nova Pro would miss it. |
| ARM64 for all containers | AgentCore Runtime runs on Graviton. Required, not optional. |
| `asyncio.gather` for 5 agents | Total wall time ≈ slowest agent. 5× faster than sequential. |
| Pydantic `AgentCommand` | Structured output enforced. No free-form parsing. |
| IDLE on timeout | Agent never raises exception. Match tick never stalls. |
| NDJSON to S3 | Append-only event log. Replay any match tick-by-tick. |

---

## Project structure

```
football-cup/
├── agents/
│   ├── shared/          # Pydantic models (shared between all agents and backend)
│   ├── goalkeeper/      # GK_01 — AgentCore Runtime container
│   ├── defender_left/   # DEF_L — AgentCore Runtime container
│   ├── defender_right/  # DEF_R — AgentCore Runtime container
│   ├── midfielder/      # MID_01 — AgentCore Runtime container
│   └── striker/         # STR_01 — AgentCore Runtime container
├── mcp_tools/           # 6 Lambda MCP tool functions (ARM64)
├── backend/             # FastAPI tick engine (ARM64 Lambda via Mangum)
├── infra/               # CDK Python — 5 stacks
├── frontend/            # Next.js 14 App Router
└── deploy.sh            # Full deployment script
```

---

## Prerequisites

- AWS CLI v2 (`aws configure` with us-east-1 default region)
- Docker with buildx + QEMU for ARM64 cross-compilation
- Python 3.11+, Node.js 18+, `jq`
- Bedrock model access: `amazon.nova-micro-v1:0` enabled in us-east-1

---

## Deploy

```bash
chmod +x deploy.sh
./deploy.sh
```

The script runs 6 phases:

1. CDK deploy `StorageStack`, `AgentCoreStack`, `McpToolsStack`
2. Build and push 5 ARM64 agent Docker images to ECR
3. Create 5 AgentCore Runtime instances (stores endpoint URIs in SSM)
4. Build and push ARM64 backend Docker image to ECR
5. CDK deploy `BackendStack` (FastAPI Lambda + API GW + WebSocket API)
6. Write `frontend/.env.local` with API and WS URLs

---

## Local development

```bash
# Backend (requires AWS credentials for DynamoDB/S3/SSM)
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # http://localhost:3000
```

---

## Start a match via API

```bash
curl -X POST https://<api-url>/match/start \
  -H "Content-Type: application/json" \
  -d '{
    "team_a": {"team_id": "team_a", "team_name": "Crimson Rovers"},
    "team_b": {"team_id": "team_b", "team_name": "Azure FC"}
  }'
```

Response:
```json
{
  "match_id": "A3F2C1B0",
  "status": "started",
  "ws_url": "wss://<ws-api-id>.execute-api.us-east-1.amazonaws.com/prod?matchId=A3F2C1B0"
}
```

Connect the frontend to the WebSocket URL and the pitch comes alive.

---

## Send a coach hint (mid-match)

```bash
curl -X POST https://<api-url>/match/A3F2C1B0/hint \
  -H "Content-Type: application/json" \
  -d '{"hint": "press higher, our striker is isolated"}'
```

The hint is injected into `game_state.human_hint` and picked up by all agents on the next tick. Agents may or may not act on it — the model decides.

---

## MCP Tools

| Tool | Purpose |
|---|---|
| `get_game_state` | DynamoDB lookup by match_id + tick |
| `get_ball_trajectory` | Physics projection N ticks forward |
| `get_nearest_opponent` | Euclidean distance sort |
| `evaluate_shot_angle` | atan2 angle + lane blocking check |
| `get_pass_success_rate` | Historical success from S3 NDJSON |
| `log_agent_decision` | Append TickEvent to S3 + DynamoDB |

---

## CDK Stacks

| Stack | Resources |
|---|---|
| `StorageStack` | DynamoDB (3 tables) + S3 events bucket |
| `AgentCoreStack` | 5 ECR repos + AgentRuntimeRole IAM |
| `McpToolsStack` | 6 Lambda MCP functions (ARM64) |
| `BackendStack` | FastAPI Lambda + HTTP API + WebSocket API |
| `FrontendStack` | Amplify SSR app |

---

## Agents

| Player | Role | Key behaviours |
|---|---|---|
| GK_01 | Goalkeeper | DIVE, CLEAR, distribute to defenders |
| DEF_L | Left Defender | MARK striker, TACKLE, INTERCEPT, CLEAR |
| DEF_R | Right Defender | Mirror DEF_L, cover right flank |
| MID_01 | Midfielder | PRESS, PASS to STR_01, link play |
| STR_01 | Striker | SHOOT early, run behind line, PRESS GK |

All agents: `amazon.nova-micro-v1:0`, 950ms timeout, IDLE fallback, structured `AgentCommand` output.

---

## Lessons from the Agentic Football Cup

- **Prompt + model choice** is the primary tuning lever, not code
- **Structured output (Pydantic) is non-negotiable** — free-form parsing fails
- **No orchestrator needed** — 5 agents reading the same world state produce coherent team play
- **Command diversity** is the single biggest performance lever
- **Tool diversity matters** — the same principle applies to production agents

---

Builder: Abilash EG — Data & AI Engineer, AWS Partner (Quadrasystems Pvt Ltd)
