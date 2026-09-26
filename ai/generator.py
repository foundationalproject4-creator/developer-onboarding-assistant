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

``OnboardingKnowledge.used_llm`` is True only when the LLM path ran and
succeeded — useful for the frontend to show "AI-enhanced" vs "basic analysis".
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Union

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

log = logging.getLogger(__name__)

# Sentinel text emitted by diagram.py when no architecture can be detected.
_DIAGRAM_UNKNOWN_SENTINEL = "Architecture not determinable from available data"


# ---------------------------------------------------------------------------
# Small normalisation helpers (handle Union[str, EntryModel] inputs)
# ---------------------------------------------------------------------------

def _file_to_explanation(f: Union[str, ImportantFileEntry]) -> ImportantFileExplanation:
    if isinstance(f, ImportantFileEntry):
        return ImportantFileExplanation(
            path=f.path,
            purpose=f.description or "Purpose not specified by analyzer.",
        )
    return ImportantFileExplanation(path=f, purpose="Purpose not specified by analyzer.")


def _dep_to_explanation(d: Union[str, DependencyEntry]) -> DependencyExplanation:
    name = d.name if isinstance(d, DependencyEntry) else d
    return DependencyExplanation(name=name, purpose="Purpose not specified by analyzer.")


def _dep_name(d: Union[str, DependencyEntry]) -> str:
    return d.name if isinstance(d, DependencyEntry) else d


# ---------------------------------------------------------------------------
# JSON fence stripping
# ---------------------------------------------------------------------------

def _strip_json_fences(text: str) -> str:
    text = text.strip()
    # Opening fence: ```json or ``` at the very start
    text = re.sub(r"^```(?:json)?", "", text).strip()
    # Closing fence: ``` optionally followed by whitespace at the very end.
    # Use re.sub with re.MULTILINE so trailing \n before ``` is handled.
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
    return text


# ---------------------------------------------------------------------------
# Fallback (rule-based) path
# ---------------------------------------------------------------------------

def _fallback_generate(analysis: RepoAnalysis) -> OnboardingKnowledge:
    notes: List[str] = []

    if analysis.project_name:
        overview = (
            f"'{analysis.project_name}' is a project using "
            f"{', '.join(analysis.languages) or 'an unspecified language'}."
        )
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

    important_files = [_file_to_explanation(f) for f in analysis.important_files]
    if not important_files:
        notes.append("important_files unavailable")

    dependencies = [_dep_to_explanation(d) for d in analysis.dependencies]
    if not dependencies:
        notes.append("dependencies unavailable")

    # The fallback path cannot generate prose architecture from project_structure
    # (that requires the LLM). Note this honestly whether or not the field is present.
    notes.append(
        "architecture: prose description unavailable in fallback mode — "
        "see architecture_diagram for a deterministic view, or enable the LLM path."
    )
    if analysis.project_structure is None:
        notes.append("project_structure unavailable")

    return OnboardingKnowledge(
        project_overview=overview,
        tech_stack=tech_stack,
        architecture=(
            "Architecture prose unavailable in fallback mode — "
            "see architecture_diagram for a deterministic structural view."
        ),
        important_files=important_files,
        dependencies=dependencies,
        setup_guide=(
            ["Not derivable from the provided analysis data."]
            if not analysis.dependencies
            else [
                f"Install dependencies: {', '.join(_dep_name(d) for d in analysis.dependencies)}.",
                "Refer to the project README (if present) for environment-specific steps.",
            ]
        ),
        development_workflow=["Not derivable from the provided analysis data."],
        starter_tasks=(
            ["Explore the important files listed above to get oriented."]
            if important_files
            else ["No specific starter tasks could be generated — important files were not provided."]
        ),
        architecture_diagram=generate_architecture_diagram(analysis),
        data_completeness_notes=notes,
        used_llm=False,
    )


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------

def _llm_generate(analysis: RepoAnalysis) -> OnboardingKnowledge:
    user_prompt = build_user_prompt(analysis)
    raw = call_llm(SYSTEM_PROMPT, user_prompt)
    cleaned = _strip_json_fences(raw)
    data = json.loads(cleaned)

    diagram = generate_architecture_diagram(analysis)
    data["architecture_diagram"] = diagram
    data["used_llm"] = True

    # If the diagram itself signals "no architecture detectable", make sure
    # data_completeness_notes reflects that even if the LLM didn't add it.
    if _DIAGRAM_UNKNOWN_SENTINEL in diagram:
        notes = data.get("data_completeness_notes") or []
        marker = "architecture_diagram: no structural signals detected"
        if marker not in notes:
            notes.append(marker)
        data["data_completeness_notes"] = notes

    return OnboardingKnowledge.model_validate(data)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_onboarding(analysis: RepoAnalysis, use_llm: bool = True) -> OnboardingKnowledge:
    if use_llm:
        try:
            return _llm_generate(analysis)
        except Exception as exc:
            # Broad catch is intentional — this is a reliability safety net so
            # the API never returns a 500 due to LLM unavailability or a bad
            # model response. Log the reason so it's visible during debugging.
            log.warning(
                "LLM path failed (%s: %s); falling back to rule-based generation.",
                type(exc).__name__,
                exc,
            )
    return _fallback_generate(analysis)
