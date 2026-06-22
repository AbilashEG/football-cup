"""
FastAPI application entry point.
Deployed as ARM64 Docker container on Lambda via Mangum adapter.
Handles both HTTP API (REST) and bootstraps WebSocket Lambda handler.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from routes.match import router as match_router
from routes.squad import router as squad_router
from routes.replay import router as replay_router
from websocket_broadcaster import websocket_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Football Cup API",
    description="Tick engine + match management for AWS Agentic Football Cup",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow Next.js frontend (Amplify + local dev)
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,https://*.amplifyapp.com",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(match_router)
app.include_router(squad_router)
app.include_router(replay_router)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "service": "football-cup-backend",
        "version": "1.0.0",
    }


@app.get("/")
async def root() -> dict:
    return {
        "message": "Football Cup API",
        "docs": "/docs",
        "endpoints": ["/match", "/squad", "/replay", "/health"],
    }


# ── Lambda handlers ───────────────────────────────────────────────────────────

# HTTP API (REST) handler via Mangum
# Mangum translates API Gateway proxy events → ASGI → FastAPI
http_handler = Mangum(app, lifespan="off")


def lambda_handler(event: dict, context) -> dict:
    """
    Unified Lambda handler:
    - Routes WebSocket lifecycle events ($connect/$disconnect/$default) to websocket_handler
    - Routes HTTP API events to Mangum/FastAPI
    """
    request_context = event.get("requestContext", {})
    route_key = request_context.get("routeKey", "")

    # WebSocket events have routeKey like $connect, $disconnect, $default
    if route_key.startswith("$"):
        logger.info(f"WebSocket event: routeKey={route_key}")
        return websocket_handler(event, context)

    # HTTP API events
    logger.info(
        f"HTTP event: {event.get('requestContext', {}).get('http', {}).get('method', 'UNKNOWN')} "
        f"{event.get('requestContext', {}).get('http', {}).get('path', '/')}"
    )
    return http_handler(event, context)
