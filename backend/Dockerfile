# FastAPI tick engine — ARM64 Lambda container
# Build: docker buildx build --platform linux/arm64 -t <ecr_uri>:latest --push .
FROM --platform=linux/arm64 public.ecr.aws/lambda/python:3.11-arm64

WORKDIR ${LAMBDA_TASK_ROOT}

# Copy shared agent models (game_state.py, command_schema.py referenced directly)
COPY agents/shared/game_state.py ./game_state.py
COPY agents/shared/command_schema.py ./command_schema.py

# Copy backend application
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/agentcore_client.py ./agentcore_client.py
COPY backend/physics.py ./physics.py
COPY backend/tick_engine.py ./tick_engine.py
COPY backend/match_logger.py ./match_logger.py
COPY backend/websocket_broadcaster.py ./websocket_broadcaster.py
COPY backend/routes/ ./routes/
COPY backend/main.py ./main.py

# Lambda handler: main.lambda_handler
CMD ["main.lambda_handler"]
