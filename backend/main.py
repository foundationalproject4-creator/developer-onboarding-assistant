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
from pydantic import BaseModel, field_validator
import uvicorn

# Import the analyzer function that Meith built.
# This must come AFTER the sys.path fix above.
from analyzer.repository_analyzer import analyze_repository

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


@app.post("/analyze", summary="Analyze repository")
def analyze(request: AnalyzeRequest) -> dict:
    """
    Accepts a repository path, runs the Repository Analyzer on it, and
    returns the full analysis result as JSON.

    On success the response looks like:
        { "status": "ok", "repo_path": "...", "total_files": ..., ... }

    On failure (bad path, permission error, etc.) a 400 Bad Request is
    returned with a JSON body: { "detail": "<error message>" }
    """
    # Call Meith's analyzer.  It never raises — errors come back as a dict
    # with status == "error" and an "error" key describing what went wrong.
    result = analyze_repository(request.repo_path)

    # If the analyzer signals an error, turn it into an HTTP 400 response
    # so the client gets a clear, standard error instead of a 200 with bad data.
    if result.get("status") == "error":
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Repository analysis failed"),
        )

    # Happy path — return the full analysis dict directly as JSON.
    return result


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
