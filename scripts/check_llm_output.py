"""
scripts/check_llm_output.py
────────────────────────────
Calls generate_onboarding(MOCK_ANALYSIS_COMPLETE, use_llm=True) against the
real Anthropic API, prints the OnboardingKnowledge as formatted JSON, then
audits every field against the grounding rules in ai/prompts.py.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python scripts/check_llm_output.py

Exit codes:
    0 — API call succeeded and no grounding violations were found.
    1 — API call succeeded but at least one violation was found.
    2 — API call failed (no key, network error, parse error, etc.).

Grounding rules checked (mirrors SYSTEM_PROMPT rules 1–7):
    Rule 1  No invented names — every tech_stack name must appear in
            analysis.languages or analysis.frameworks.
    Rule 1  No invented file paths — every important_files[].path must
            appear in analysis.important_files.
    Rule 1  No invented dep names — every dependencies[].name must
            appear in analysis.dependencies.
    Rule 2  Empty lists in output for empty input lists — if the input
            has no important_files / dependencies, the output lists must
            also be empty.
    Rule 5  setup_guide / development_workflow must only reference names
            that actually exist in the input; any step that introduces a
            token not present in the serialised input is flagged.
    Rule 6  architecture must not be non-sentinel when project_structure
            is null and important_files is empty (not triggered here since
            the complete mock has both, but the checker is wired in).
    Rule 7  dependencies[].purpose must not reference version or type
            strings (e.g. "0.115.12", "prod") — those fields must not
            be used to infer purpose per rule 7.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Allow running from the project root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.generator import generate_onboarding
from ai.mock_data import MOCK_ANALYSIS_COMPLETE
from ai.schemas import DependencyEntry, ImportantFileEntry, OnboardingKnowledge, RepoAnalysis

# ── Helpers ──────────────────────────────────────────────────────────────────

SENTINEL_PHRASES = {
    "not derivable from the provided analysis data",
    "not available",
    "unavailable",
    "insufficient data",
    "not provided by the analyzer",
    "not specified by analyzer",
    "not determinable from available data",
}


def _is_sentinel(text: str) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in SENTINEL_PHRASES)


def _known_dep_names(analysis: RepoAnalysis) -> set[str]:
    return {
        (d.name if isinstance(d, DependencyEntry) else d).lower()
        for d in analysis.dependencies
    }


def _known_file_paths(analysis: RepoAnalysis) -> set[str]:
    return {
        (f.path if isinstance(f, ImportantFileEntry) else f).lower()
        for f in analysis.important_files
    }


def _known_tokens(analysis: RepoAnalysis) -> set[str]:
    """
    All string tokens that are legitimately present in the analysis input.
    Used for setup_guide / development_workflow checks — any word in those
    fields must be traceable to at least one of these tokens (or be a
    common article/preposition that couldn't carry invented meaning).
    """
    tokens: set[str] = set()
    if analysis.project_name:
        tokens.update(analysis.project_name.lower().split("-"))
        tokens.add(analysis.project_name.lower())
    for lang in analysis.languages:
        tokens.add(lang.lower())
    for fw in analysis.frameworks:
        tokens.add(fw.lower())
    for d in analysis.dependencies:
        name = (d.name if isinstance(d, DependencyEntry) else d).lower()
        tokens.add(name)
    for f in analysis.important_files:
        path = (f.path if isinstance(f, ImportantFileEntry) else f).lower()
        tokens.add(path)
        tokens.update(Path(path).parts)
        tokens.add(Path(path).stem)
    if isinstance(analysis.project_structure, dict):
        for k, vs in analysis.project_structure.items():
            tokens.add(k.lower())
            if isinstance(vs, list):
                tokens.update(v.lower() for v in vs if isinstance(v, str))
    elif isinstance(analysis.project_structure, list):
        for p in analysis.project_structure:
            tokens.add(str(p).lower())
    # Common words that carry no invented meaning
    tokens.update({
        "the", "a", "an", "and", "or", "of", "in", "to", "for", "with",
        "is", "are", "be", "run", "use", "your", "this", "that", "it",
        "all", "any", "by", "on", "at", "from", "as", "if", "so",
        "dependencies", "dependency", "install", "project", "file", "files",
        "entry", "point", "main", "app", "application", "readme", "refer",
        "environment", "specific", "steps", "present", "server", "http",
        "start", "running", "pip", "python", "node", "npm", "yarn",
        "setup", "guide", "available", "not", "no", "provided",
        "requirements", "txt", "py", "ts", "js",
        # Hyphen-joined compounds that split cleanly into known words above
        "environment-specific",
    })
    return tokens


# ── Grounding checks ─────────────────────────────────────────────────────────

class Violation:
    def __init__(self, rule: str, field: str, detail: str):
        self.rule = rule
        self.field = field
        self.detail = detail

    def __str__(self) -> str:
        return f"  [Rule {self.rule}] {self.field}: {self.detail}"


def check_grounding(
    result: OnboardingKnowledge,
    analysis: RepoAnalysis,
) -> list[Violation]:
    violations: list[Violation] = []
    known_langs_fws = {s.lower() for s in analysis.languages + analysis.frameworks}
    known_dep_names = _known_dep_names(analysis)
    known_file_paths = _known_file_paths(analysis)
    known_tokens = _known_tokens(analysis)

    # ── Rule 1: tech_stack names must come from languages or frameworks ───────
    for item in result.tech_stack:
        if item.name.lower() not in known_langs_fws:
            violations.append(Violation(
                "1", "tech_stack",
                f"'{item.name}' is not in analysis.languages or analysis.frameworks "
                f"(known: {sorted(known_langs_fws)})",
            ))

    # ── Rule 1: important_files paths must come from analysis ─────────────────
    for f in result.important_files:
        if f.path.lower() not in known_file_paths:
            violations.append(Violation(
                "1", "important_files",
                f"'{f.path}' is not in analysis.important_files "
                f"(known paths: {sorted(known_file_paths)})",
            ))

    # ── Rule 1: dependency names must come from analysis ─────────────────────
    for d in result.dependencies:
        if d.name.lower() not in known_dep_names:
            violations.append(Violation(
                "1", "dependencies",
                f"'{d.name}' is not in analysis.dependencies "
                f"(known names: {sorted(known_dep_names)})",
            ))

    # ── Rule 2: empty input → empty output (files) ────────────────────────────
    if not analysis.important_files and result.important_files:
        violations.append(Violation(
            "2", "important_files",
            f"Input has no important_files but output has {len(result.important_files)} entries.",
        ))

    # ── Rule 2: empty input → empty output (deps) ────────────────────────────
    if not analysis.dependencies and result.dependencies:
        violations.append(Violation(
            "2", "dependencies",
            f"Input has no dependencies but output has {len(result.dependencies)} entries.",
        ))

    # ── Rule 5: setup_guide / development_workflow token check ───────────────
    # We only flag steps that are non-sentinel and contain tokens not present
    # anywhere in the input.  We look for multi-word proper-noun-style tokens
    # (capitalised, length > 3) that aren't in known_tokens — these are the
    # most likely source of invented content (invented tool names, commands, etc.).
    def _flag_invented_tokens(steps: list[str], field: str) -> None:
        import re as _re
        for step in steps:
            if _is_sentinel(step):
                continue
            for word in step.split():
                # Strip punctuation; also split on hyphens so "environment-specific"
                # is checked as "environment" and "specific" individually.
                clean = word.strip(".,;:()/").lower()
                sub_words = _re.split(r"[-]", clean)
                # A step is only suspicious if ALL sub-words of a token are unknown.
                if all(
                    len(sub) > 3
                    and sub not in known_tokens
                    and not sub.replace(".", "").replace("-", "").isdigit()
                    for sub in sub_words
                ) and clean not in known_tokens:
                    violations.append(Violation(
                        "5", field,
                        f"Step {step!r} contains token {word!r} not traceable to input data.",
                    ))
                    break  # one flag per step is enough

    _flag_invented_tokens(result.setup_guide, "setup_guide")
    _flag_invented_tokens(result.development_workflow, "development_workflow")

    # ── Rule 6: architecture sentinel when no structure/files ─────────────────
    if analysis.project_structure is None and not analysis.important_files:
        if not _is_sentinel(result.architecture):
            violations.append(Violation(
                "6", "architecture",
                "project_structure is null and important_files is empty, but architecture "
                f"is a non-sentinel string: {result.architecture!r}",
            ))

    # ── Rule 7: dep purpose must not reference version/type strings ──────────
    version_and_type_tokens: set[str] = set()
    for d in analysis.dependencies:
        if isinstance(d, DependencyEntry):
            if d.version:
                version_and_type_tokens.add(d.version.lower())
                # also flag major.minor components
                parts = d.version.split(".")
                if len(parts) >= 2:
                    version_and_type_tokens.add(f"{parts[0]}.{parts[1]}")
            if d.type:
                version_and_type_tokens.add(d.type.lower())

    for item in result.dependencies:
        purpose_lower = item.purpose.lower()
        for token in version_and_type_tokens:
            if token in purpose_lower:
                violations.append(Violation(
                    "7", "dependencies",
                    f"'{item.name}'.purpose {item.purpose!r} references "
                    f"version/type token {token!r} (rule 7 forbids this).",
                ))

    return violations


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    analysis = MOCK_ANALYSIS_COMPLETE

    print("─" * 64)
    print("INPUT  (MOCK_ANALYSIS_COMPLETE)")
    print("─" * 64)
    print(json.dumps(analysis.model_dump(exclude_none=False), indent=2))
    print()

    print("─" * 64)
    print("Calling generate_onboarding(use_llm=True) …")
    print("─" * 64)

    try:
        result = generate_onboarding(analysis, use_llm=True)
    except Exception as exc:
        print(f"\n✗  API call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if not result.used_llm:
        print(
            "\n⚠  used_llm=False — the LLM path failed silently and the fallback "
            "was used. Check ANTHROPIC_API_KEY and network access.",
            file=sys.stderr,
        )
        return 2

    print()
    print("─" * 64)
    print("OUTPUT  (OnboardingKnowledge)")
    print("─" * 64)
    print(json.dumps(result.model_dump(), indent=2))
    print()

    # ── Grounding audit ───────────────────────────────────────────────────────
    violations = check_grounding(result, analysis)

    print("─" * 64)
    print("GROUNDING AUDIT")
    print("─" * 64)

    if result.data_completeness_notes:
        print("ℹ  data_completeness_notes (model's own admissions):")
        for note in result.data_completeness_notes:
            print(f"    • {note}")
        print()

    if not violations:
        print("✓  No grounding violations detected.")
        print()
        print(
            "Note: this checker audits structural invariants (no invented names,\n"
            "paths, or dep names; sentinel rules; version-token rule). It cannot\n"
            "detect subtly misleading prose — read the 'architecture' and\n"
            "'project_overview' fields manually to confirm they stay within the\n"
            "bounds of the input data above."
        )
        return 0

    print(f"✗  {len(violations)} grounding violation(s) found:\n")
    for v in violations:
        print(v)
    print()
    print(
        "Note: rule-5 token checks flag words not present in the input data.\n"
        "Review flagged steps — some common words may be false positives, but\n"
        "any tool name, command, or path that isn't in the input above is real."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
