"""
Developer Onboarding Assistant - Backend
FastAPI application entry point.
"""

import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError, field_validator
import uvicorn

# ---------------------------------------------------------------------------
# Path fix — make analyzer/ and ai/ importable when the server is started
# from the project root OR from inside the backend/ sub-directory.
# ---------------------------------------------------------------------------
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ---------------------------------------------------------------------------
# Project imports — must come AFTER the sys.path fix above.
# ---------------------------------------------------------------------------
from analyzer.repository_analyzer import analyze_repository
from analyzer.repository_cloner import analyze_remote_repository, is_repo_url
from backend.analyzer_adapter import to_repo_analysis
from ai.generator import generate_onboarding
from ai.schemas import OnboardingKnowledge, RepoAnalysis

# Import Radhika's AI router — registered below after app + middleware setup.
from ai.router import router as ai_router

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Developer Onboarding Assistant - Backend",
    description="Backend API for the IBM Bob 2.0 Hackathon - Developer Onboarding Assistant",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — allow the Vercel frontend (and local dev) to call this API.
#
# ALLOWED_ORIGINS is read from the environment so the Render dashboard can
# set it to the real Vercel URL without touching code.  During local dev the
# default covers the standard Vite port.
#
# Format: comma-separated list of origins, e.g. in the Render dashboard:
#   ALLOWED_ORIGINS=https://your-app.vercel.app
# ---------------------------------------------------------------------------
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Radhika's AI router.  Exposes POST /ai/generate.
# Placed after middleware so CORS headers apply to /ai/* routes as well.
app.include_router(ai_router)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    repo_url: str

    @field_validator("repo_url")
    @classmethod
    def repo_url_must_be_valid(cls, v: str) -> str:
        # Delegate to the module-level validator so the same logic
        # is used whether the value arrives via Pydantic or directly.
        return _validate_repo_url(v)


class HealthResponse(BaseModel):
    status: str
    version: str


# ---------------------------------------------------------------------------
# URL validation helper
# ---------------------------------------------------------------------------

def _validate_repo_url(repo_url: str) -> str:
    """
    Validate that *repo_url* is a public HTTPS URL on GitHub, GitLab, or
    Bitbucket.  Raises ``ValueError`` (caught by Pydantic) on failure.

    Uses is_repo_url() from the repository_cloner module so that validation
    logic is defined in exactly one place.
    """
    if not repo_url or not repo_url.strip():
        raise ValueError("repo_url must not be blank")

    value = repo_url.strip()

    if not is_repo_url(value):
        raise ValueError(
            "repo_url must be a public HTTPS URL from GitHub, GitLab, or "
            "Bitbucket (e.g. https://github.com/owner/repository)"
        )

    return value


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", summary="Root")
def root() -> dict:
    """Simple liveness check — confirms the backend is running."""
    return {"message": "Developer Onboarding Assistant backend is running"}


@app.get("/health", response_model=HealthResponse, summary="Health check")
def health() -> HealthResponse:
    """Returns current health status and API version."""
    return HealthResponse(status="ok", version=app.version)


@app.post(
    "/analyze",
    response_model=OnboardingKnowledge,
    summary="Analyze repository",
)
def analyze(request: AnalyzeRequest) -> OnboardingKnowledge:
    """
    Clone a public repository, analyze it, adapt the analyzer output,
    generate onboarding knowledge, and return the structured result.

    The repository is cloned into a temporary directory by the
    repository_cloner module, which deletes it automatically after analysis
    whether the analysis succeeds or fails.

    On failure a 400 or 500 response is returned with a JSON body:
        { "detail": "<error message>" }
    """
    # analyze_remote_repository() handles cloning, analysis, and cleanup.
    # It never raises — errors come back as {"status": "error", "error": "..."}.
    raw_result = analyze_remote_repository(request.repo_url)

    if raw_result.get("status") == "error":
        raise HTTPException(
            status_code=400,
            detail=raw_result.get("error", "Repository analysis failed"),
        )

    # Convert the analyzer's native dict shape into the RepoAnalysis schema.
    try:
        analysis_dict = to_repo_analysis(raw_result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to process repository analysis results.",
        ) from exc

    # Validate the converted dict against the Pydantic model.
    try:
        analysis = RepoAnalysis.model_validate(analysis_dict)
    except ValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail="Repository analysis does not match the expected schema.",
        ) from exc

    # Generate and return the onboarding knowledge.
    try:
        return generate_onboarding(analysis)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate onboarding knowledge.",
        ) from exc


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Render (and most cloud platforms) inject a PORT environment variable.
    # Fall back to 8000 for local development.
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
