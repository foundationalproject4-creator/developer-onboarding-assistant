"""
FastAPI router for the AI Analysis + Architecture layer.

Kushal integrates this with two lines in backend/main.py:

    from ai.router import router as ai_router
    app.include_router(ai_router)

This does NOT modify backend/main.py — that wiring is a one-time, tiny
change for Kushal to make himself when he's ready.
"""

from fastapi import APIRouter

from .generator import generate_onboarding
from .schemas import OnboardingKnowledge, RepoAnalysis

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/generate", response_model=OnboardingKnowledge, summary="Generate onboarding knowledge")
def generate(analysis: RepoAnalysis) -> OnboardingKnowledge:
    """
    Accepts the Repository Analyzer's output and returns structured
    onboarding knowledge for the frontend to render.
    """
    return generate_onboarding(analysis)
