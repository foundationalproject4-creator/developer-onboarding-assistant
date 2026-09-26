"""
Data contracts for the AI Analysis + Architecture layer.

INPUT  : RepoAnalysis        -> what Meith's Repository Analyzer is expected to hand us.
OUTPUT : OnboardingKnowledge  -> what we hand back to Kushal's backend / Mayank's frontend.

These are intentionally flexible on the input side (Meith's analyzer isn't built yet),
and strict on the output side (so backend + frontend always get a predictable shape).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# INPUT: Repository Analyzer contract
# ---------------------------------------------------------------------------

class ImportantFileEntry(BaseModel):
    path: str
    description: Optional[str] = None


class DependencyEntry(BaseModel):
    name: str
    version: Optional[str] = None
    type: Optional[str] = None  # e.g. "prod", "dev"


class RepoAnalysis(BaseModel):
    """
    Expected shape of the Repository Analyzer's output.

    Fields accept either simple strings or the richer entry objects above,
    since we don't yet know exactly what Meith's analyzer will emit.
    Anything missing should simply be left out / None — we never guess it.
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
    name: str
    category: Optional[str] = None  # "language" | "framework" | "tool" | etc.
    role: str


class ImportantFileExplanation(BaseModel):
    path: str
    purpose: str


class DependencyExplanation(BaseModel):
    name: str
    purpose: str


class OnboardingKnowledge(BaseModel):
    project_overview: str
    tech_stack: List[TechStackItem] = Field(default_factory=list)
    architecture: str
    important_files: List[ImportantFileExplanation] = Field(default_factory=list)
    dependencies: List[DependencyExplanation] = Field(default_factory=list)
    setup_guide: List[str] = Field(default_factory=list)
    development_workflow: List[str] = Field(default_factory=list)
    starter_tasks: List[str] = Field(default_factory=list)
    architecture_diagram: str  # Mermaid syntax

    # Not in the original spec, but required by the "don't invent info" rule:
    # explicit list of what we couldn't say anything about, so the frontend
    # can render "Not available from repo analysis" instead of us guessing.
    data_completeness_notes: List[str] = Field(default_factory=list)
