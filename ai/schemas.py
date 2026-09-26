"""
Data contracts for the AI Analysis + Architecture layer.

INPUT  : RepoAnalysis        -> what Meith's Repository Analyzer is expected to hand us.
OUTPUT : OnboardingKnowledge  -> what we hand back to Kushal's backend / Mayank's frontend.

These are intentionally flexible on the input side (Meith's analyzer isn't built yet),
and strict on the output side (so backend + frontend always get a predictable shape).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# INPUT: Repository Analyzer contract
# ---------------------------------------------------------------------------

class ImportantFileEntry(BaseModel):
    """A file the analyzer considers important enough to highlight."""

    path: str
    description: Optional[str] = None
    """Human-readable description of the file's role. May be None if the
    analyzer detected the file but did not produce a description."""


class DependencyEntry(BaseModel):
    """A single project dependency as reported by the analyzer."""

    name: str
    version: Optional[str] = None
    """Semver string if known (e.g. ``"0.115.12"``), otherwise None."""
    type: Optional[Literal["prod", "dev", "peer", "optional"]] = None
    """Dependency category. ``"prod"`` = runtime, ``"dev"`` = development-only.
    None if the analyzer did not classify it."""


class RepoAnalysis(BaseModel):
    """
    Expected shape of the Repository Analyzer's output.

    Fields accept either simple strings or the richer entry objects above,
    since we don't yet know exactly what Meith's analyzer will emit.
    Anything missing should simply be left out / None — we never guess it.

    ``project_structure`` can be either:

    * a nested dict tree, e.g. ``{"src": ["index.ts", "app.ts"], "tests": [...]}``
    * a flat list of paths, e.g. ``["src/index.ts", "src/app.ts"]``

    Either form is forwarded verbatim to the LLM as part of the user prompt.
    """

    project_name: Optional[str] = None
    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    important_files: List[Union[str, ImportantFileEntry]] = Field(default_factory=list)
    dependencies: List[Union[str, DependencyEntry]] = Field(default_factory=list)
    # project_structure can be a nested tree (dict) or a flat list of paths.
    project_structure: Optional[Union[Dict[str, Any], List[str]]] = None


# ---------------------------------------------------------------------------
# OUTPUT: AI layer contract
# ---------------------------------------------------------------------------

class TechStackItem(BaseModel):
    """One technology (language, framework, or tool) used in the project."""

    name: str
    category: Optional[str] = None
    """Broad category: ``"language"``, ``"framework"``, ``"tool"``, etc.
    None when the AI layer could not classify it."""
    role: str
    """One-sentence description of what this technology does in the project."""


class ImportantFileExplanation(BaseModel):
    """An important file with a plain-English explanation of its purpose."""

    path: str
    purpose: str
    """Plain-English explanation of why this file matters to a new developer."""


class DependencyExplanation(BaseModel):
    """A dependency with a plain-English explanation of why it is used."""

    name: str
    purpose: str
    """Plain-English explanation of the dependency's role in this project."""


class OnboardingKnowledge(BaseModel):
    """
    Structured onboarding knowledge returned by ``POST /ai/generate``.

    Every field is either directly derived from the ``RepoAnalysis`` input or
    contains an explicit sentinel string such as
    ``"Not derivable from the provided analysis data."``
    No field is ever invented — check ``data_completeness_notes`` for a list
    of any sections that could not be filled from the available input.

    ``architecture_diagram`` is a Mermaid ``graph TD`` string. Pass it directly
    to any Mermaid renderer (mermaid.js ``render()``, react-mermaid2, etc.).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_overview": "my-app is a web application using FastAPI and React.",
                "tech_stack": [
                    {"name": "FastAPI", "category": "framework", "role": "Python web framework serving the REST API."},
                    {"name": "React", "category": "framework", "role": "Frontend UI library."},
                ],
                "architecture": "The project has a React frontend communicating with a FastAPI backend.",
                "important_files": [
                    {"path": "backend/main.py", "purpose": "FastAPI application entry point."}
                ],
                "dependencies": [
                    {"name": "fastapi", "purpose": "Web framework used to build the REST API."}
                ],
                "setup_guide": ["Install dependencies: fastapi, uvicorn, pydantic, anthropic."],
                "development_workflow": ["Not derivable from the provided analysis data."],
                "starter_tasks": ["Explore the important files listed above to get oriented."],
                "architecture_diagram": "graph TD\n    Frontend[\"Frontend\"]\n    Backend[\"Backend / API\"]\n    Frontend --> Backend",
                "used_llm": True,
                "data_completeness_notes": [],
            }
        }
    )

    project_overview: str
    tech_stack: List[TechStackItem] = Field(default_factory=list)
    architecture: str
    important_files: List[ImportantFileExplanation] = Field(default_factory=list)
    dependencies: List[DependencyExplanation] = Field(default_factory=list)
    setup_guide: List[str] = Field(default_factory=list)
    development_workflow: List[str] = Field(default_factory=list)
    starter_tasks: List[str] = Field(default_factory=list)
    architecture_diagram: str
    """Mermaid ``graph TD`` syntax string. Render with mermaid.js or equivalent."""

    used_llm: bool = False
    """``True`` when the Anthropic LLM path ran and succeeded; ``False`` when
    the rule-based fallback was used (no API key, or any LLM/parse error).
    Frontend can use this to show an "AI-enhanced" badge vs "basic analysis"."""

    # Not in the original spec, but required by the "don't invent info" rule:
    # explicit list of what we couldn't say anything about, so the frontend
    # can render "Not available from repo analysis" instead of us guessing.
    data_completeness_notes: List[str] = Field(default_factory=list)
    """List of field names or sections that could not be filled from the input.
    Empty list means all sections were grounded. Frontend should surface these
    as 'Not available from repo analysis' rather than leaving sections blank."""
