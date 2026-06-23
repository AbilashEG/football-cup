# Player Lambda — Lambda base image (ARM64)
# ✅ public.ecr.aws/lambda/python:3.12  (Lambda base — correct for Lambda functions)
# ✅ CMD ["handler.handler"]            (Lambda handler style — correct for Lambda)
# ✅ ARM64 (built by CodeBuild ARM_CONTAINER)
# Build from repo root with build arg:
#   docker build --build-arg PLAYER=goalkeeper -f players/Dockerfile .

FROM public.ecr.aws/lambda/python:3.12

ARG PLAYER
ENV PLAYER=${PLAYER}

# Install deps
COPY players/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt --no-cache-dir

# Copy shared Pydantic models
COPY agents/shared/ ${LAMBDA_TASK_ROOT}/shared/

# Copy the specific player handler
COPY players/${PLAYER}/handler.py ${LAMBDA_TASK_ROOT}/handler.py

ENV PYTHONPATH=${LAMBDA_TASK_ROOT}:${LAMBDA_TASK_ROOT}/shared

# ✅ Lambda handler entry point
CMD ["handler.handler"]
