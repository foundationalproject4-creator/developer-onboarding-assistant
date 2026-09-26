"""
FastAPI router for the AI Analysis + Architecture layer.

Kushal integrates this with two lines in backend/main.py:

    from ai.router import router as ai_router
    app.include_router(ai_router)

This does NOT modify backend/main.py — that wiring is a one-time, tiny
change for Kushal to make himself when he's ready.

Rate limiting
-------------
This endpoint performs an LLM call (expensive, ~1-3s latency). Without rate
limiting a single client can exhaust the Anthropic quota and delay all other
users.

SlowAPI (a Starlette / FastAPI-native rate-limiter built on limits) is the
recommended approach:

    pip install slowapi

Then in backend/main.py:

    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

And decorate the route:

    @router.post("/generate")
    @limiter.limit("10/minute")   # adjust for your expected load
    async def generate(request: Request, analysis: RepoAnalysis) -> OnboardingKnowledge:
        ...

The route below is ready to accept that decorator.  The ``request: Request``
parameter is needed by SlowAPI but can be added at integration time without
changing any other code here.

Alternative: a reverse-proxy (nginx / AWS API Gateway / Cloudflare) is the
right place to enforce rate limits for a multi-tenant deployment, and
requires no application code at all.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from .generator import async_generate_onboarding
from .metrics import ai_metrics
from .schemas import OnboardingKnowledge, RepoAnalysis

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/generate",
    response_model=OnboardingKnowledge,
    summary="Generate onboarding knowledge",
    response_description=(
        "Structured onboarding knowledge derived from the repository analysis. "
        "All fields are grounded in the input data. "
        "Check `data_completeness_notes` for any fields that could not be filled "
        "from the provided analysis — those will contain explicit sentinel strings "
        "rather than invented content. "
        "`architecture_diagram` is a Mermaid graph string ready to pass to any "
        "Mermaid renderer (e.g. mermaid.js, react-mermaid2)."
    ),
)
async def generate(request: Request, analysis: RepoAnalysis) -> OnboardingKnowledge:
    """
    Accepts the Repository Analyzer's JSON output and returns structured
    onboarding knowledge for the frontend to render.

    **LLM behaviour:** uses the Anthropic API (async) when ``ANTHROPIC_API_KEY``
    is set in the environment. If the key is absent or the API call fails for
    any reason, the endpoint automatically falls back to a deterministic
    rule-based path — it never returns a 500 due to LLM unavailability.

    **Caching:** identical requests (same repo analysis hash) are served from
    an in-memory TTL cache, skipping the LLM call entirely.

    **Async endpoint:** the handler is ``async def`` so FastAPI does not block
    the event loop during the LLM call, allowing concurrent requests to be
    served normally.

    **Rate limiting:** see module docstring for SlowAPI integration guidance.
    """
    request_id = str(uuid.uuid4())
    t0 = time.monotonic()

    try:
        result = await async_generate_onboarding(analysis, _request_id=request_id)
        latency_ms = (time.monotonic() - t0) * 1000
        path = "llm" if result.used_llm else "fallback"

        log.info(
            "ai.generate completed",
            extra={
                "json_fields": {
                    "event": "ai.generate.ok",
                    "request_id": request_id,
                    "path": path,
                    "latency_ms": round(latency_ms, 1),
                    "used_llm": result.used_llm,
                    "project_name": analysis.project_name,
                }
            },
        )
        ai_metrics.record(path=path, latency_ms=latency_ms)
        return result

    except Exception as exc:  # pragma: no cover — belt-and-suspenders safety net
        latency_ms = (time.monotonic() - t0) * 1000
        log.error(
            "ai.generate failed",
            extra={
                "json_fields": {
                    "event": "ai.generate.error",
                    "request_id": request_id,
                    "latency_ms": round(latency_ms, 1),
                    # Deliberately exclude exc details from the HTTP response to
                    # avoid leaking internal implementation info; they're in logs.
                    "error_type": type(exc).__name__,
                }
            },
        )
        ai_metrics.record(path="error", latency_ms=latency_ms)
        raise HTTPException(status_code=500, detail="Onboarding generation failed.") from exc
