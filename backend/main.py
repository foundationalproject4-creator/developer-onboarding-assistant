"""
Developer Onboarding Assistant - Backend
FastAPI application entry point.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError, field_validator

# Make analyzer/ and ai/ importable from the project root.
_project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from analyzer.repository_analyzer import analyze_repository
from backend.analyzer_adapter import to_repo_analysis
from ai.generator import generate_onboarding
from ai.schemas import OnboardingKnowledge, RepoAnalysis


app = FastAPI(
    title="Developer Onboarding Assistant - Backend",
    description="Backend API for the IBM Bob 2.0 Hackathon - Developer Onboarding Assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class AnalyzeRequest(BaseModel):
    repo_url: str

    @field_validator("repo_url")
    @classmethod
    def repo_url_must_be_valid(cls, v: str) -> str:
        return _validate_repo_url(v)


class HealthResponse(BaseModel):
    status: str
    version: str


def _validate_repo_url(repo_url: str) -> str:
    if not repo_url or not repo_url.strip():
        raise ValueError("repo_url must not be blank")

    value = repo_url.strip()
    parsed = urlparse(value)

    if parsed.scheme.lower() != "https":
        raise ValueError("repo_url must use HTTPS")

    if parsed.username or parsed.password:
        raise ValueError(
            "repo_url must not include credentials; "
            "use a GitHub, GitLab, or Bitbucket HTTPS URL"
        )

    allowed_hosts = {"github.com", "gitlab.com", "bitbucket.org"}
    hostname = (parsed.hostname or "").lower()

    if hostname not in allowed_hosts:
        raise ValueError(
            "repo_url host must be GitHub, GitLab, or Bitbucket"
        )

    if not parsed.path or parsed.path == "/":
        raise ValueError("repo_url must include a repository path")

    return value


def _clone_repository(repo_url: str) -> str:
    temp_dir = tempfile.mkdtemp(prefix="onboarding_repo_")

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--", repo_url, temp_dir],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail="Git is not installed or not available on PATH",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="Repository clone timed out",
        ) from exc
    except OSError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start git clone: {exc}",
        ) from exc

    if result.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)

        stderr = (result.stderr or "").strip()
        detail = "Could not clone repository"

        if stderr:
            detail += f": {stderr[:300]}"

        raise HTTPException(status_code=400, detail=detail)

    return temp_dir


@app.get("/", summary="Root")
def root() -> dict:
    """Simple liveness check."""
    return {
        "message": "Developer Onboarding Assistant backend is running"
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
)
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
    """

    repo_dir = _clone_repository(request.repo_url)

    try:
        result = analyze_repository(repo_dir)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=400,
                detail=result.get(
                    "error",
                    "Repository analysis failed",
                ),
            )

        try:
            analysis_dict = to_repo_analysis(result)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="Failed to process repository analysis results.",
            ) from exc

        try:
            analysis = RepoAnalysis.model_validate(analysis_dict)
        except ValidationError as exc:
            raise HTTPException(
                status_code=500,
                detail="Repository analysis does not match the expected schema.",
            ) from exc

        try:
            return generate_onboarding(analysis)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate onboarding knowledge.",
            ) from exc

    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )