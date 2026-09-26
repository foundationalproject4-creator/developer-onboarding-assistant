#!/usr/bin/env python3
"""
scripts/check_llm_output.py — Grounding audit for live LLM outputs.

Usage:
    python scripts/check_llm_output.py <analysis_json_file> [--output <output_json_file>]

This script:
1. Reads a RepoAnalysis from a JSON file (or stdin with -).
2. Calls the AI module to generate OnboardingKnowledge (uses real LLM if
   ANTHROPIC_API_KEY is set, falls back to rule-based otherwise).
3. Runs the grounding audit: checks that every tech_stack name, important
   file path, and dependency name in the output was present in the input.
4. Exits 0 if no failures, exits 1 if any grounding failures are detected.

Designed to be run in CI against a set of real repo analyses to catch
regressions when the prompt or model is updated.

Example:
    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/check_llm_output.py sample_analysis.json

Sample analysis JSON (save as sample_analysis.json):
    {
        "project_name": "my-app",
        "languages": ["Python"],
        "frameworks": ["FastAPI"],
        "dependencies": [{"name": "fastapi"}, {"name": "pydantic"}],
        "important_files": [{"path": "main.py", "description": "Entry point"}]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a script from the repo root without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.generator import generate_onboarding, _grounding_audit_failures
from ai.schemas import RepoAnalysis


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run grounding audit on AI-generated onboarding output."
    )
    parser.add_argument(
        "analysis",
        metavar="ANALYSIS_JSON",
        help="Path to a RepoAnalysis JSON file, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--output",
        metavar="OUTPUT_JSON",
        default=None,
        help="Optional path to write the OnboardingKnowledge JSON output.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        default=False,
        help="Skip the LLM call and use the rule-based fallback only.",
    )
    args = parser.parse_args()

    # --- Load analysis ---
    if args.analysis == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.analysis).read_text(encoding="utf-8")

    try:
        analysis = RepoAnalysis.model_validate_json(raw)
    except Exception as exc:
        print(f"ERROR: Failed to parse RepoAnalysis: {exc}", file=sys.stderr)
        return 2

    print(f"Project: {analysis.project_name or '(unnamed)'}")
    print(f"Languages: {analysis.languages}")
    print(f"Frameworks: {analysis.frameworks}")
    print(f"Dependencies: {len(analysis.dependencies)}")
    print(f"Important files: {len(analysis.important_files)}")
    print()

    # --- Generate ---
    result = generate_onboarding(analysis, use_llm=not args.no_llm)
    print(f"Path used: {'LLM' if result.used_llm else 'fallback (rule-based)'}")
    print()

    # --- Grounding audit ---
    failures = _grounding_audit_failures(result, analysis)

    if failures:
        print(f"GROUNDING FAILURES ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
    else:
        print("Grounding audit: PASSED — no hallucinated names detected.")

    # --- Completeness notes ---
    if result.data_completeness_notes:
        print()
        print("Data completeness notes:")
        for note in result.data_completeness_notes:
            print(f"  * {note}")

    # --- Optional output ---
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
        print()
        print(f"Output written to: {out_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
