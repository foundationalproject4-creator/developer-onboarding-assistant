"""
Developer Onboarding Assistant — Backend
FastAPI application entry point.
"""

import sys
import os

# ---------------------------------------------------------------------------
# Path fix — make sure "analyzer/" is importable when the server is started
# from the project root (developer-onboarding-assistant/) OR from inside
# the backend/ sub-directory.
#
# Directory layout:
#   developer-onboarding-assistant/
#       analyzer/repository_analyzer.py   ← Meith's module
#       backend/main.py                   ← this file
#
# When uvicorn is launched from the project root the working directory is
# already on sys.path, so the import works automatically.  When it is
# launched from inside backend/ we add the parent directory explicitly.
# ---------------------------------------------------------------------------
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError, field_validator
import uvicorn

# Import the analyzer function that Meith built.
# This must come AFTER the sys.path fix above.
from analyzer.repository_analyzer import analyze_repository

# Import the adapter and the AI layer.
# Both imports must come AFTER the sys.path fix so the project root is on sys.path.
from backend.analyzer_adapter import to_repo_analysis
from ai.generator import generate_onboarding
from ai.schemas import OnboardingKnowledge, RepoAnalysis

app = FastAPI(
    title="Developer Onboarding Assistant API",
    description="Backend API for the IBM Bob 2.0 Hackathon — Developer Onboarding Assistant",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    repo_path: str

    @field_validator("repo_path")
    @classmethod
    def repo_path_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("repo_path must not be blank")
        return v.strip()


class HealthResponse(BaseModel):
    status: str
    version: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", summary="Root")
def root() -> dict:
    """Simple liveness check — confirms the backend is running."""
    return {"message": "Developer Onboarding Assistant backend is running"}


@app.get("/health", response_model=HealthResponse, summary="Health check")
def health() -> HealthResponse:
    """Returns the current health status and API version."""
    return HealthResponse(status="ok", version=app.version)


@app.post("/analyze", response_model=OnboardingKnowledge, summary="Analyze repository")
def analyze(request: AnalyzeRequest) -> OnboardingKnowledge:
    """
    Accepts a repository path, runs the Repository Analyzer on it, adapts
    the result for the AI layer, generates onboarding knowledge, and returns
    the structured ``OnboardingKnowledge`` as JSON.

    On failure a 4xx/5xx is returned with a JSON body:
        { "detail": "<error message>" }
    """
    # ------------------------------------------------------------------
    # 1. Run the Repository Analyzer.  Never raises — errors are in the dict.
    # ------------------------------------------------------------------
    result = analyze_repository(request.repo_path)

    if result.get("status") == "error":
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Repository analysis failed"),
        )

    # ------------------------------------------------------------------
    # 2. Adapt the analyzer output to the AI layer's RepoAnalysis shape.
    # ------------------------------------------------------------------
    try:
        analysis_dict = to_repo_analysis(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail="Failed to process repository analysis results."
        ) from exc

    # ------------------------------------------------------------------
    # 3. Validate against the RepoAnalysis Pydantic model.
    # ------------------------------------------------------------------
    try:
        analysis = RepoAnalysis.model_validate(analysis_dict)
    except ValidationError as exc:
        raise HTTPException(
            status_code=500, detail="Repository analysis data failed schema validation."
        ) from exc

    # ------------------------------------------------------------------
    # 4. Generate onboarding knowledge (LLM path with rule-based fallback).
    # ------------------------------------------------------------------
    try:
        knowledge = generate_onboarding(analysis)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail="Failed to generate onboarding knowledge."
        ) from exc

    return knowledge


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
