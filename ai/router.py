"""
FastAPI router for the AI Analysis + Architecture layer.

Kushal integrates this with two lines in backend/main.py:

    from ai.router import router as ai_router
    app.include_router(ai_router)

This does NOT modify backend/main.py — that wiring is a one-time, tiny
change for Kushal to make himself when he's ready.
"""

from fastapi import APIRouter, HTTPException

from .generator import generate_onboarding
from .schemas import OnboardingKnowledge, RepoAnalysis

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
def generate(analysis: RepoAnalysis) -> OnboardingKnowledge:
    """
    Accepts the Repository Analyzer's JSON output and returns structured
    onboarding knowledge for the frontend to render.

    **LLM behaviour:** uses the Anthropic API when ``ANTHROPIC_API_KEY`` is set
    in the environment. If the key is absent or the API call fails for any
    reason, the endpoint automatically falls back to a deterministic rule-based
    path — it never returns a 500 due to LLM unavailability.

    **Sync endpoint:** kept synchronous intentionally; the LLM call is blocking
    but isolated to this route, so it does not hold up other endpoints.
    """
    try:
        return generate_onboarding(analysis)
    except Exception as exc:  # pragma: no cover — belt-and-suspenders safety net
        raise HTTPException(status_code=500, detail=f"Onboarding generation failed: {exc}") from exc
