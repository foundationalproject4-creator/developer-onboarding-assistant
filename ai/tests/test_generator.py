"""
Tests for the ai/ module.

Run with: python -m pytest ai/tests/

Offline tests (no API key needed) force use_llm=False to exercise the
grounded fallback path.  LLM-path tests mock call_llm / acall_llm directly
so they never hit the network.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai.generator import (
    _CACHE_TTL_SECONDS,
    _cache,
    _cache_get,
    _cache_key,
    _cache_set,
    _dep_name,
    _dep_to_explanation,
    _file_to_explanation,
    _strip_json_fences,
    async_generate_onboarding,
    generate_onboarding,
)
from ai.llm_client import (
    LLMUnavailableError,
    _extract_tool_input,
    _is_transient,
    _log_usage,
    call_llm,
)
from ai.mock_data import MOCK_ANALYSIS_COMPLETE, MOCK_ANALYSIS_SPARSE
from ai.schemas import DependencyEntry, ImportantFileEntry, OnboardingKnowledge, RepoAnalysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_result(**overrides) -> Dict[str, Any]:
    """Minimal valid dict that OnboardingKnowledge.model_validate accepts."""
    base: Dict[str, Any] = {
        "project_overview": "Test overview",
        "tech_stack": [],
        "architecture": "Test architecture",
        "important_files": [],
        "dependencies": [],
        "setup_guide": ["run tests"],
        "development_workflow": ["commit and push"],
        "starter_tasks": ["read the README"],
        "data_completeness_notes": [],
        # generator adds these after the call:
        "architecture_diagram": "graph TD\n    Unknown[\"dummy\"]",
        "used_llm": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fallback path — grounded output
# ---------------------------------------------------------------------------

def test_complete_analysis_produces_grounded_output():
    result = generate_onboarding(MOCK_ANALYSIS_COMPLETE, use_llm=False)
    assert "developer-onboarding-assistant" in result.project_overview
    names = {item.name for item in result.tech_stack}
    assert "FastAPI" in names and "Python" in names
    assert any(f.path == "backend/main.py" for f in result.important_files)
    assert "Frontend" in result.architecture_diagram
    assert "Backend" in result.architecture_diagram
    # anthropic dep triggers the external-service node in the diagram
    assert "Anthropic" in result.architecture_diagram


def test_sparse_analysis_reports_gaps_instead_of_inventing():
    result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    assert "important_files unavailable" in result.data_completeness_notes
    assert "dependencies unavailable" in result.data_completeness_notes
    assert result.important_files == []
    assert result.dependencies == []


def test_fallback_always_notes_architecture_limitation():
    """Fallback can't write architecture prose — must note this in data_completeness_notes."""
    for analysis in (MOCK_ANALYSIS_COMPLETE, MOCK_ANALYSIS_SPARSE):
        result = generate_onboarding(analysis, use_llm=False)
        assert any("architecture" in note for note in result.data_completeness_notes), (
            f"Expected architecture note in data_completeness_notes, got: {result.data_completeness_notes}"
        )
        assert "fallback" in result.architecture.lower(), (
            f"architecture field should reference fallback mode, got: {result.architecture}"
        )


# ---------------------------------------------------------------------------
# Hallucination-fix regression tests
# ---------------------------------------------------------------------------

def test_setup_guide_with_deps_names_them_explicitly():
    """setup_guide must list actual dependency names, not generic prose."""
    result = generate_onboarding(MOCK_ANALYSIS_COMPLETE, use_llm=False)
    assert any(
        "fastapi" in step.lower() or "uvicorn" in step.lower() or "pydantic" in step.lower()
        for step in result.setup_guide
    ), f"setup_guide did not mention any known dep names: {result.setup_guide}"


def test_setup_guide_sentinel_when_no_deps():
    """When dependencies is empty the fallback must emit the sentinel, not generic steps."""
    result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    assert result.setup_guide == ["Not derivable from the provided analysis data."], (
        f"Expected sentinel for sparse input, got: {result.setup_guide}"
    )


def test_development_workflow_is_always_sentinel_in_fallback():
    """Fallback must never invent workflow steps — always the sentinel string."""
    for analysis in (MOCK_ANALYSIS_COMPLETE, MOCK_ANALYSIS_SPARSE):
        result = generate_onboarding(analysis, use_llm=False)
        assert result.development_workflow == ["Not derivable from the provided analysis data."], (
            f"development_workflow was not the sentinel: {result.development_workflow}"
        )


# ---------------------------------------------------------------------------
# Union branch tests
# ---------------------------------------------------------------------------

def test_file_to_explanation_plain_string():
    """_file_to_explanation must handle a bare string path, not just ImportantFileEntry."""
    result = _file_to_explanation("src/main.py")
    assert result.path == "src/main.py"
    assert result.purpose == "Purpose not specified by analyzer."


def test_file_to_explanation_entry_with_description():
    entry = ImportantFileEntry(path="src/app.py", description="App entry point.")
    result = _file_to_explanation(entry)
    assert result.path == "src/app.py"
    assert result.purpose == "App entry point."


def test_dep_to_explanation_plain_string():
    """_dep_to_explanation must handle a bare string name, not just DependencyEntry."""
    result = _dep_to_explanation("requests")
    assert result.name == "requests"
    assert result.purpose == "Purpose not specified by analyzer."


def test_dep_name_plain_string():
    assert _dep_name("flask") == "flask"
    assert _dep_name(DependencyEntry(name="flask", version="3.0.0")) == "flask"


def test_plain_string_deps_flow_through_fallback():
    """Plain-string deps in RepoAnalysis must appear in setup_guide and dependencies."""
    analysis = RepoAnalysis(project_name="test", languages=["Python"], dependencies=["requests", "click"])
    result = generate_onboarding(analysis, use_llm=False)
    dep_names = {d.name for d in result.dependencies}
    assert dep_names == {"requests", "click"}
    assert "requests" in result.setup_guide[0]
    assert "click" in result.setup_guide[0]


# ---------------------------------------------------------------------------
# _strip_json_fences (kept for backward compat — no longer used internally)
# ---------------------------------------------------------------------------

def test_strip_json_fences_clean_json():
    raw = '{"key": "value"}'
    assert _strip_json_fences(raw) == raw


def test_strip_json_fences_with_json_prefix():
    raw = "```json\n{\"key\": \"value\"}\n```"
    assert _strip_json_fences(raw) == '{"key": "value"}'


def test_strip_json_fences_trailing_newline_before_fence():
    """Claude sometimes emits a trailing newline before the closing fence."""
    raw = "```json\n{\"key\": \"value\"}\n```\n"
    assert _strip_json_fences(raw) == '{"key": "value"}'


def test_strip_json_fences_plain_fence():
    raw = "```\n{\"key\": \"value\"}\n```"
    assert _strip_json_fences(raw) == '{"key": "value"}'


# ---------------------------------------------------------------------------
# used_llm field
# ---------------------------------------------------------------------------

def test_fallback_sets_used_llm_false():
    result = generate_onboarding(MOCK_ANALYSIS_COMPLETE, use_llm=False)
    assert result.used_llm is False


def test_fallback_sparse_sets_used_llm_false():
    result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    assert result.used_llm is False


# ---------------------------------------------------------------------------
# schema_version field
# ---------------------------------------------------------------------------

def test_repo_analysis_has_schema_version():
    analysis = RepoAnalysis()
    assert analysis.schema_version == 1


def test_onboarding_knowledge_has_schema_version():
    result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    assert result.schema_version == 1


def test_schema_version_present_in_llm_path():
    """schema_version must be set even when the LLM path runs."""
    with patch("ai.generator.call_llm", return_value=_make_llm_result()):
        result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=True)
    assert result.schema_version == 1


# ---------------------------------------------------------------------------
# LLM path (sync) — mocked
# ---------------------------------------------------------------------------

def test_llm_path_used_llm_true():
    with patch("ai.generator.call_llm", return_value=_make_llm_result()):
        result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=True)
    assert result.used_llm is True
    assert result.project_overview == "Test overview"


def test_llm_path_failure_falls_back():
    """If call_llm raises, generate_onboarding must fall back without raising."""
    _cache.clear()  # Ensure no cached result from prior tests interferes.
    with patch("ai.generator.call_llm", side_effect=LLMUnavailableError("no key")):
        result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=True)
    assert result.used_llm is False


# ---------------------------------------------------------------------------
# LLM path (async) — mocked
# ---------------------------------------------------------------------------

def test_async_llm_path_used_llm_true():
    _cache.clear()
    async def _run():
        with patch("ai.generator.acall_llm", new_callable=AsyncMock,
                   return_value=_make_llm_result()):
            return await async_generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=True)
    result = asyncio.run(_run())
    assert result.used_llm is True


def test_async_llm_path_failure_falls_back():
    _cache.clear()  # Ensure no cached result from prior tests interferes.
    async def _run():
        with patch("ai.generator.acall_llm", new_callable=AsyncMock,
                   side_effect=LLMUnavailableError("no key")):
            return await async_generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=True)
    result = asyncio.run(_run())
    assert result.used_llm is False


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

def _clear_cache():
    _cache.clear()


def test_cache_miss_then_hit():
    """Second identical call must return the cached result without calling the LLM."""
    _clear_cache()
    call_count = 0

    def _fake_call_llm(system, user):
        nonlocal call_count
        call_count += 1
        return _make_llm_result()

    with patch("ai.generator.call_llm", side_effect=_fake_call_llm):
        r1 = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=True)
        r2 = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=True)

    assert call_count == 1, "LLM should only be called once; second call must use cache"
    assert r1.project_overview == r2.project_overview


def test_cache_key_differs_for_different_inputs():
    k1 = _cache_key(MOCK_ANALYSIS_COMPLETE)
    k2 = _cache_key(MOCK_ANALYSIS_SPARSE)
    assert k1 != k2


def test_cache_ttl_expiry(monkeypatch):
    """After TTL expires the cache entry is treated as a miss."""
    _clear_cache()
    key = _cache_key(MOCK_ANALYSIS_SPARSE)
    fake_result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    _cache_set(key, fake_result)

    # Wind the clock forward past TTL using monkeypatch on time.monotonic.
    original_monotonic = time.monotonic
    expired_time = original_monotonic() + _CACHE_TTL_SECONDS + 1
    monkeypatch.setattr(time, "monotonic", lambda: expired_time)

    assert _cache_get(key) is None, "Expired entry must be treated as a miss"


def test_cache_hit_before_expiry(monkeypatch):
    """Before TTL expires the cache entry is returned."""
    _clear_cache()
    key = _cache_key(MOCK_ANALYSIS_SPARSE)
    fake_result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    _cache_set(key, fake_result)

    # No time travel — should be a cache hit.
    assert _cache_get(key) is fake_result


# ---------------------------------------------------------------------------
# llm_client internals
# ---------------------------------------------------------------------------

def test_extract_tool_input_success():
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"project_overview": "x"}
    response = MagicMock()
    response.content = [block]
    result = _extract_tool_input(response)
    assert result["project_overview"] == "x"


def test_extract_tool_input_no_tool_block():
    response = MagicMock()
    response.content = []
    try:
        _extract_tool_input(response)
        assert False, "Should have raised LLMUnavailableError"
    except LLMUnavailableError:
        pass


def test_is_transient_returns_false_without_anthropic():
    """Without anthropic installed _is_transient must return False gracefully."""
    # We can't easily uninstall anthropic, but we can test its behaviour
    # with a plain RuntimeError (which is neither transient nor auth).
    assert _is_transient(RuntimeError("some random error")) is False


def test_call_llm_no_api_key():
    """call_llm must raise LLMUnavailableError immediately when no key is set."""
    import os
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        try:
            call_llm("system", "user")
            assert False, "Should have raised"
        except LLMUnavailableError as e:
            assert "ANTHROPIC_API_KEY" in str(e)
    finally:
        if original is not None:
            os.environ["ANTHROPIC_API_KEY"] = original


def test_log_usage_does_not_raise_on_bad_response():
    """_log_usage must not raise even if usage attr is missing."""
    _log_usage(object())  # plain object has no .usage — should be silent


if __name__ == "__main__":
    # Quick smoke-run for the offline tests.
    test_complete_analysis_produces_grounded_output()
    test_sparse_analysis_reports_gaps_instead_of_inventing()
    test_fallback_always_notes_architecture_limitation()
    test_setup_guide_with_deps_names_them_explicitly()
    test_setup_guide_sentinel_when_no_deps()
    test_development_workflow_is_always_sentinel_in_fallback()
    test_file_to_explanation_plain_string()
    test_file_to_explanation_entry_with_description()
    test_dep_to_explanation_plain_string()
    test_dep_name_plain_string()
    test_plain_string_deps_flow_through_fallback()
    test_strip_json_fences_clean_json()
    test_strip_json_fences_with_json_prefix()
    test_strip_json_fences_trailing_newline_before_fence()
    test_strip_json_fences_plain_fence()
    test_fallback_sets_used_llm_false()
    test_fallback_sparse_sets_used_llm_false()
    test_repo_analysis_has_schema_version()
    test_onboarding_knowledge_has_schema_version()
    test_schema_version_present_in_llm_path()
    test_llm_path_used_llm_true()
    test_llm_path_failure_falls_back()
    test_async_llm_path_used_llm_true()
    test_async_llm_path_failure_falls_back()
    test_cache_miss_then_hit()
    test_cache_key_differs_for_different_inputs()
    test_call_llm_no_api_key()
    test_extract_tool_input_success()
    test_extract_tool_input_no_tool_block()
    test_is_transient_returns_false_without_anthropic()
    test_log_usage_does_not_raise_on_bad_response()
    print("All tests passed.")
