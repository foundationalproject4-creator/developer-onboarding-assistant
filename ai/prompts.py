"""
Prompt construction for the onboarding-knowledge generator.

Design principle (this is the part IBM Bob was used to pressure-test):
the model is given ONLY the analyzer JSON, told explicitly to treat it as
the sole source of truth, and instructed to say a field is unavailable
rather than invent plausible-sounding detail. The diagram is deliberately
excluded from the LLM's job — that's generated separately, deterministically
(see diagram.py) — because free-text generation of a diagram is exactly
where hallucinated connections tend to appear.
"""

from __future__ import annotations

import json

from .schemas import RepoAnalysis

SYSTEM_PROMPT = """You are an assistant that helps a new developer understand an \
unfamiliar codebase. You will be given structured data extracted by an automated \
repository analyzer. This data is your ONLY source of truth.

Rules you must follow:
1. Never invent file names, dependency purposes, frameworks, or architecture \
details that are not present in the provided data or that cannot be reasonably \
inferred directly from it.
2. If a section cannot be filled in from the given data (e.g. no important_files \
were provided), say so plainly instead of guessing — and add a short note about \
it to `data_completeness_notes`.
3. Keep explanations practical and aimed at a developer who has never seen this \
project before: what it is, what it's built with, where to start, what to run.
4. Respond with ONLY a single JSON object matching the schema below. No markdown \
fences, no commentary, no text before or after the JSON.

Output JSON schema:
{
  "project_overview": string,
  "tech_stack": [{"name": string, "category": string|null, "role": string}],
  "architecture": string,
  "important_files": [{"path": string, "purpose": string}],
  "dependencies": [{"name": string, "purpose": string}],
  "setup_guide": [string],
  "development_workflow": [string],
  "starter_tasks": [string],
  "data_completeness_notes": [string]
}

Do NOT include an "architecture_diagram" field — that is generated separately.
"""


def build_user_prompt(analysis: RepoAnalysis) -> str:
    payload = analysis.model_dump(exclude_none=False)
    return (
        "Repository analysis data (JSON):\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        "Using ONLY the data above, produce the JSON object described in your "
        "instructions. If a list above is empty or a field is null, treat that "
        "as 'not available' for that part of the output — do not fill it in "
        "from general knowledge of common project layouts."
    )
