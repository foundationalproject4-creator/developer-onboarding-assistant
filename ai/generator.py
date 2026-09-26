"""
Main entry point for the AI Analysis + Architecture layer.

    from ai.generator import generate_onboarding
    knowledge = generate_onboarding(repo_analysis)

Two paths:
1. LLM path — used when ANTHROPIC_API_KEY is set. The model turns the raw
   analyzer data into readable explanations, constrained by the prompt rules
   in prompts.py.
2. Fallback path — used when no API key is configured, or if the LLM call
   fails / returns invalid JSON. This is a purely rule-based assembly of the
   same output shape directly from the analyzer fields. It's less polished
   in prose but 100% grounded, so the rest of the team (and demo) is never
   blocked on API access.

Both paths always run the diagram generator separately and deterministically
(see diagram.py) rather than trusting the LLM to draw it.
"""

from __future__ import annotations

import json
import re
from typing import List

from .diagram import generate_architecture_diagram
from .llm_client import LLMUnavailableError, call_llm
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schemas import (
    DependencyEntry,
    DependencyExplanation,
    ImportantFileEntry,
    ImportantFileExplanation,
    OnboardingKnowledge,
    RepoAnalysis,
    TechStackItem,
)


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def _fallback_generate(analysis: RepoAnalysis) -> OnboardingKnowledge:
    notes: List[str] = []

    if analysis.project_name:
        overview = f"'{analysis.project_name}' is a project using {', '.join(analysis.languages) or 'an unspecified language'}."
    else:
        overview = "Project name was not provided by the repository analyzer."
        notes.append("project_name unavailable")

    tech_stack: List[TechStackItem] = []
    for lang in analysis.languages:
        tech_stack.append(TechStackItem(name=lang, category="language", role="Used in this project."))
    for fw in analysis.frameworks:
        tech_stack.append(TechStackItem(name=fw, category="framework", role="Used in this project."))
    if not tech_stack:
        notes.append("languages/frameworks unavailable")

    important_files: List[ImportantFileExplanation] = []
    for f in analysis.important_files:
        if isinstance(f, ImportantFileEntry):
            important_files.append(ImportantFileExplanation(
                path=f.path,
                purpose=f.description or "Purpose not specified by analyzer.",
            ))
        else:
            important_files.append(ImportantFileExplanation(path=f, purpose="Purpose not specified by analyzer."))
    if not important_files:
        notes.append("important_files unavailable")

    dependencies: List[DependencyExplanation] = []
    for d in analysis.dependencies:
        if isinstance(d, DependencyEntry):
            dependencies.append(DependencyExplanation(name=d.name, purpose="Purpose not specified by analyzer."))
        else:
            dependencies.append(DependencyExplanation(name=d, purpose="Purpose not specified by analyzer."))
    if not dependencies:
        notes.append("dependencies unavailable")

    if analysis.project_structure is None:
        notes.append("project_structure unavailable")

    return OnboardingKnowledge(
        project_overview=overview,
        tech_stack=tech_stack,
        architecture="Architecture description unavailable — repository analyzer did not "
                      "provide enough structural detail to describe it beyond the diagram below.",
        important_files=important_files,
        dependencies=dependencies,
        setup_guide=["No setup instructions available from repository analysis."] if not analysis.dependencies else [
            "Install project dependencies.",
            "Refer to project README (if present) for environment-specific steps.",
        ],
        development_workflow=["Not enough information to describe a development workflow."],
        starter_tasks=["Explore the important files listed above to get oriented."] if important_files else [
            "No specific starter tasks could be generated — important files were not provided."
        ],
        architecture_diagram=generate_architecture_diagram(analysis),
        data_completeness_notes=notes,
    )


def _llm_generate(analysis: RepoAnalysis) -> OnboardingKnowledge:
    user_prompt = build_user_prompt(analysis)
    raw = call_llm(SYSTEM_PROMPT, user_prompt)
    cleaned = _strip_json_fences(raw)
    data = json.loads(cleaned)
    data["architecture_diagram"] = generate_architecture_diagram(analysis)
    return OnboardingKnowledge.model_validate(data)


def generate_onboarding(analysis: RepoAnalysis, use_llm: bool = True) -> OnboardingKnowledge:
    if use_llm:
        try:
            return _llm_generate(analysis)
        except (LLMUnavailableError, json.JSONDecodeError, Exception):
            # Any failure here falls back rather than breaking the API response.
            # (Broad except is intentional: this is a hackathon reliability
            # safety net, not something we want silently propagating 500s.)
            pass
    return _fallback_generate(analysis)
