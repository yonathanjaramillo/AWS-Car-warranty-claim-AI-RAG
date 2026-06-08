# ARM64 — matches Bedrock AgentCore container runtime spec
# WHY ARM64 (tell Mike): AgentCore requires ARM64 containers.
# Building for ARM64 from the start means no surprise rebuild at deploy time.
FROM python:3.12-slim as base

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.8.3
RUN poetry config virtualenvs.create false

# Dependencies first (layer cache)
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-interaction --no-ansi --no-root --only main

# App code
COPY app/ ./app/

# Non-root user — least privilege even inside the container
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check — ECS uses this to route traffic
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
