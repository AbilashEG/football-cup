# ✅ Base image  : python:3.12-slim  (NOT Lambda base image)
# ✅ Port        : 8080
# ✅ Entry point : CMD ["python", "agent.py"]
# ✅ Health check: GET /health returns 200
# ✅ Architecture: ARM64 (built via CodeBuild ARM_CONTAINER)
# ❌ NOT public.ecr.aws/lambda/python — NEVER use Lambda base image
# ❌ NOT CMD ["handler"] Lambda style
# ❌ NO hardcoded credentials

FROM python:3.12-slim

WORKDIR /app

# System deps — curl for health probe, clean up apt cache
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared Pydantic models (required by agent.py at import time)
# Build context must be repo root: docker build -f coach/Dockerfile .
COPY agents/shared /app/shared

# Install Python dependencies
COPY coach/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy coach agent entry point
COPY coach/agent.py /app/agent.py

# AgentCore Runtime contract: port 8080
EXPOSE 8080

# Health check — AgentCore Runtime startup probe polls /health
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s \
  CMD curl -f http://localhost:8080/health || exit 1

# ✅ CMD uses python directly (NOT Lambda handler style)
CMD ["python", "agent.py"]
