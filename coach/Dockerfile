# AgentCore Runtime — python:3.12-slim (NOT Lambda base image)
# Build from repo root:
#   docker build --platform linux/arm64 -f coach/Dockerfile -t <ecr_uri>:latest .
# (CodeBuild ARM_CONTAINER builds this natively — no --platform flag needed)

FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared Pydantic models (build context = repo root)
COPY agents/shared/ /app/shared/

# Install deps
COPY coach/requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt --no-cache-dir

# Copy agent entry point
COPY coach/agent.py /app/agent.py

ENV PYTHONPATH=/app:/app/shared

# AgentCore Runtime: port 8080
EXPOSE 8080

# AgentCore health probe hits /health
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s \
    CMD curl -f http://localhost:8080/health || exit 1

# ✅ python directly — NOT uvicorn, NOT Lambda handler
CMD ["python", "agent.py"]
