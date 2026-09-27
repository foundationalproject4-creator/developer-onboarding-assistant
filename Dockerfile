# Dockerfile — developer-onboarding-assistant
#
# Builds the FastAPI backend together with the ai/ module.
# The ai/ module is not a standalone service — it is a Python package imported
# by the backend.  A single image runs both.
#
# Usage:
#   docker build -t onboarding-assistant .
#   docker run --env-file .env -p 8000:8000 onboarding-assistant
#
# Required at runtime:
#   ANTHROPIC_API_KEY  — Anthropic API key for the LLM path.
#                        If absent, the rule-based fallback is used automatically.
#
# Optional at runtime (see .env.example for all variables):
#   AI_MAX_REQUESTS    — Hard cap on LLM calls per process lifetime (0 = unlimited).

FROM python:3.13-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Minimal OS hardening: run as a non-root user.
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# Install Python dependencies first (better layer caching).
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source.
# ai/ is a sibling of backend/ and must be on PYTHONPATH.
COPY backend/ ./backend/
COPY analyzer/ ./analyzer/
COPY ai/ ./ai/

# ai/ needs to be importable as a top-level package from backend/main.py.
ENV PYTHONPATH=/app

USER app

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
