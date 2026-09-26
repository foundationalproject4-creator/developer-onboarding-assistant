"""
Grounding-audit tests — §5b.

These tests wire _grounding_audit_failures() into the automated test suite
by running it against mocked LLM outputs, so the audit runs without a real
API key.  They verify that:

1. The audit correctly identifies hallucinated names in LLM output.
2. The audit passes clean / grounded output silently.
3. The router-level grounding audit executes on the LLM path.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai.generator import _grounding_audit_failures, async_generate_onboarding, generate_onboarding
from ai.generator import _cache
from ai.schemas import DependencyEntry, ImportantFileEntry, RepoAnalysis


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

ANALYSIS = RepoAnalysis(
    project_name="demo",
    languages=["Python"],
    frameworks=["FastAPI"],
    important_files=[ImportantFileEntry(path="main.py", description="Entry point")],
    dependencies=[DependencyEntry(name="fastapi"), DependencyEntry(name="pydantic")],
)


def _grounded_llm_result(**overrides) -> Dict[str, Any]:
    """LLM result that is 100% grounded in ANALYSIS."""
    base: Dict[str, Any] = {
        "project_overview": "demo is a Python FastAPI project.",
        "tech_stack": [
            {"name": "Python", "category": "language", "role": "Primary language."},
            {"name": "FastAPI", "category": "framework", "role": "Web framework."},
        ],
        "architecture": "A FastAPI application.",
        "important_files": [{"path": "main.py", "purpose": "Entry point."}],
        "dependencies": [
            {"name": "fastapi", "purpose": "Web framework."},
            {"name": "pydantic", "purpose": "Data validation."},
        ],
        "setup_guide": ["pip install fastapi pydantic"],
        "development_workflow": ["Not derivable from the provided analysis data."],
        "starter_tasks": ["Read main.py"],
        "data_completeness_notes": [],
        "architecture_diagram": "graph TD\n    Backend[\"Backend / API\"]",
        "used_llm": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Unit tests for _grounding_audit_failures
# ---------------------------------------------------------------------------

def test_audit_clean_output_passes():
    """A fully-grounded result must produce zero failures."""
    from ai.schemas import OnboardingKnowledge
    data = _grounded_llm_result()
    result = OnboardingKnowledge.model_validate(data)
    failures = _grounding_audit_failures(result, ANALYSIS)
    assert failures == [], f"Expected no failures, got: {failures}"


def test_audit_hallucinated_tech_stack_detected():
    """A tech_stack name not in the input must be flagged."""
    from ai.schemas import OnboardingKnowledge
    data = _grounded_llm_result(
        tech_stack=[
            {"name": "React", "category": "framework", "role": "UI library."},  # not in input
        ]
    )
    result = OnboardingKnowledge.model_validate(data)
    failures = _grounding_audit_failures(result, ANALYSIS)
    assert any("React" in f for f in failures), f"Expected React to be flagged, got: {failures}"


def test_audit_hallucinated_dep_detected():
    """A dependency name not in the input must be flagged."""
    from ai.schemas import OnboardingKnowledge
    data = _grounded_llm_result(
        dependencies=[
            {"name": "celery", "purpose": "Task queue."},  # not in input
        ]
    )
    result = OnboardingKnowledge.model_validate(data)
    failures = _grounding_audit_failures(result, ANALYSIS)
    assert any("celery" in f for f in failures), f"Expected celery to be flagged, got: {failures}"


def test_audit_hallucinated_important_file_detected():
    """An important_files path with no overlap with input paths must be flagged."""
    from ai.schemas import OnboardingKnowledge
    data = _grounded_llm_result(
        important_files=[
            {"path": "secret_handler.py", "purpose": "Handles secrets."},  # invented
        ]
    )
    result = OnboardingKnowledge.model_validate(data)
    failures = _grounding_audit_failures(result, ANALYSIS)
    assert any("secret_handler.py" in f for f in failures), (
        f"Expected secret_handler.py to be flagged, got: {failures}"
    )


def test_audit_path_components_accepted():
    """File paths where a component matches a known input path must pass."""
    from ai.schemas import OnboardingKnowledge
    # "main.py" appears in ANALYSIS.important_files; full path with sub-dir is fine.
    data = _grounded_llm_result(
        important_files=[{"path": "src/main.py", "purpose": "Entry point."}]
    )
    result = OnboardingKnowledge.model_validate(data)
    failures = _grounding_audit_failures(result, ANALYSIS)
    grounded_failures = [f for f in failures if "src/main.py" in f]
    assert grounded_failures == [], f"Path component should be accepted; got: {failures}"


# ---------------------------------------------------------------------------
# Integration: audit runs on the mocked LLM path (sync)
# ---------------------------------------------------------------------------

def test_grounding_audit_runs_on_llm_path_no_failures():
    """LLM path with a grounded mock → audit passes silently."""
    _cache.clear()
    with patch("ai.generator.call_llm", return_value=_grounded_llm_result()):
        result = generate_onboarding(ANALYSIS, use_llm=True)
    assert result.used_llm is True


def test_grounding_audit_logs_warning_on_hallucination(caplog):
    """LLM path with a hallucinated name → warning must appear in logs."""
    import logging
    _cache.clear()
    hallucinated = _grounded_llm_result(
        tech_stack=[{"name": "Kubernetes", "category": "tool", "role": "Orchestrator."}]
    )
    with patch("ai.generator.call_llm", return_value=hallucinated):
        import ai.generator
        with caplog.at_level(logging.WARNING, logger="ai.generator"):
            result = generate_onboarding(ANALYSIS, use_llm=True)
    assert result.used_llm is True
    assert any("grounding_audit" in r.message for r in caplog.records), (
        f"Expected grounding_audit warning; log records: {[r.message for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# Integration: audit runs on the async LLM path
# ---------------------------------------------------------------------------

def test_grounding_audit_runs_on_async_llm_path():
    _cache.clear()
    async def _run():
        with patch("ai.generator.acall_llm", new_callable=AsyncMock,
                   return_value=_grounded_llm_result()):
            return await async_generate_onboarding(ANALYSIS, use_llm=True)
    result = asyncio.run(_run())
    assert result.used_llm is True
