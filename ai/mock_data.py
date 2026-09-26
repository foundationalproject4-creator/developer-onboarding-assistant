"""
Mock Repository Analyzer outputs.

Use these to develop and test the AI module before Meith's real analyzer
is available. MOCK_ANALYSIS_COMPLETE has rich data; MOCK_ANALYSIS_SPARSE
has big gaps, to verify the "say unavailable, don't invent" behavior.
"""

from .schemas import DependencyEntry, ImportantFileEntry, RepoAnalysis

MOCK_ANALYSIS_COMPLETE = RepoAnalysis(
    project_name="developer-onboarding-assistant",
    languages=["Python", "TypeScript"],
    frameworks=["FastAPI", "React"],
    important_files=[
        ImportantFileEntry(path="backend/main.py", description="FastAPI app entry point"),
        ImportantFileEntry(path="backend/requirements.txt", description="Python dependencies"),
    ],
    dependencies=[
        DependencyEntry(name="fastapi", version="0.115.12", type="prod"),
        DependencyEntry(name="uvicorn", version="0.34.2", type="prod"),
        DependencyEntry(name="pydantic", version="2.11.4", type="prod"),
        DependencyEntry(name="anthropic", version="0.25.0", type="prod"),
    ],
    project_structure={
        "backend": ["main.py", "requirements.txt", "README.md"],
    },
)

MOCK_ANALYSIS_SPARSE = RepoAnalysis(
    project_name="mystery-project",
    languages=["Python"],
    # everything else deliberately empty/missing
)
