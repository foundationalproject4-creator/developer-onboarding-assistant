"""
Developer Onboarding Assistant — Backend
FastAPI application entry point.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
import uvicorn

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


class AnalyzeResponse(BaseModel):
    message: str
    repo_path: str


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


@app.post("/analyze", response_model=AnalyzeResponse, summary="Analyze repository")
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Accepts a repository path and queues it for analysis.

    This endpoint is intentionally a placeholder — the Repository Analyzer
    (implemented separately) will be wired in here once available.
    """
    # TODO: invoke the Repository Analyzer once Meith's module is ready.
    return AnalyzeResponse(
        message="Repository analysis started",
        repo_path=request.repo_path,
    )


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
