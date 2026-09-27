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
    _fallback_overview,
    _fallback_workflow,
    _file_to_explanation,
    _normalised_paths,
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
# _fallback_overview — improved project overview
# ---------------------------------------------------------------------------

def test_overview_includes_project_name_and_language():
    """Overview must mention both the project name and primary language."""
    result = generate_onboarding(MOCK_ANALYSIS_COMPLETE, use_llm=False)
    assert "developer-onboarding-assistant" in result.project_overview
    assert "Python" in result.project_overview


def test_overview_includes_frameworks_when_present():
    """Overview must mention detected frameworks."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Python"],
        frameworks=["FastAPI", "React"],
    )
    overview = _fallback_overview(analysis)
    assert "FastAPI" in overview
    assert "React" in overview


def test_overview_includes_top_dirs_from_dict_structure():
    """Plain dir→files dict: keys are used as directory names."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Python"],
        project_structure={"backend": ["main.py"], "frontend": ["App.jsx"]},
    )
    overview = _fallback_overview(analysis)
    assert "backend" in overview
    assert "frontend" in overview


def test_overview_uses_top_level_dirs_value_not_metadata_keys():
    """When project_structure contains a 'top_level_dirs' key, use its values
    rather than the metadata key names (type, has_tests, has_ci, etc.)."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Python"],
        project_structure={
            "top_level_dirs": ["backend", "frontend", "tests"],
            "type": "monorepo",
            "has_tests": True,
            "has_ci": True,
            "has_docker": False,
            "entry_points": ["backend/main.py"],
        },
    )
    overview = _fallback_overview(analysis)
    # Real directory names from the list must appear
    assert "backend" in overview
    assert "frontend" in overview
    assert "tests" in overview
    # Metadata keys must not appear as directory names
    for noise_key in ("type", "has_tests", "has_ci", "has_docker", "entry_points"):
        assert noise_key not in overview, (
            f"Metadata key {noise_key!r} should not appear in overview: {overview!r}"
        )


def test_overview_includes_top_dirs_from_flat_list_structure():
    """When project_structure is a flat path list, unique top-level dirs appear."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["TypeScript"],
        project_structure=["src/index.ts", "src/app.ts", "tests/test_app.ts"],
    )
    overview = _fallback_overview(analysis)
    assert "src" in overview
    assert "tests" in overview


def test_overview_falls_back_to_important_files_for_dirs():
    """When project_structure is absent, derive dirs from important_files paths."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Go"],
        important_files=[
            ImportantFileEntry(path="cmd/main.go", description="Entry point"),
            ImportantFileEntry(path="pkg/router.go", description="Router"),
        ],
    )
    overview = _fallback_overview(analysis)
    assert "cmd" in overview
    assert "pkg" in overview


def test_overview_includes_key_dependencies():
    """Overview must list all dependency names."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Python"],
        dependencies=[
            DependencyEntry(name="fastapi"),
            DependencyEntry(name="uvicorn"),
            DependencyEntry(name="pydantic"),
        ],
    )
    overview = _fallback_overview(analysis)
    assert "fastapi" in overview
    assert "uvicorn" in overview
    assert "pydantic" in overview


def test_overview_lists_all_deps_without_truncation():
    """All dependency names must appear — no 'and X more' abbreviation."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Python"],
        dependencies=[DependencyEntry(name=f"dep{i}") for i in range(8)],
    )
    overview = _fallback_overview(analysis)
    for i in range(8):
        assert f"dep{i}" in overview, f"dep{i} missing from overview: {overview!r}"
    assert "more" not in overview, f"'more' should not appear: {overview!r}"


def test_overview_lists_all_deps_large_set():
    """Even with 17 deps every name must appear — no count suffix."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Python"],
        dependencies=[DependencyEntry(name=f"lib{i}") for i in range(17)],
    )
    overview = _fallback_overview(analysis)
    for i in range(17):
        assert f"lib{i}" in overview, f"lib{i} missing from overview: {overview!r}"
    assert "more" not in overview, f"'more' should not appear: {overview!r}"


def test_overview_no_name_no_language_uses_fallback_sentence():
    """When neither name nor language is detected, a safe sentinel is used."""
    analysis = RepoAnalysis()
    overview = _fallback_overview(analysis)
    assert len(overview) > 0
    # Must not invent a name or language
    assert "developer-onboarding-assistant" not in overview


def test_overview_no_name_with_language():
    """When only language is known, the overview must still be grounded."""
    analysis = RepoAnalysis(languages=["Rust"])
    overview = _fallback_overview(analysis)
    assert "Rust" in overview


def test_overview_name_only_no_language():
    """When only the project name is known, no language must be invented."""
    analysis = RepoAnalysis(project_name="mystery-project")
    overview = _fallback_overview(analysis)
    assert "mystery-project" in overview
    # Should not claim any language
    assert "Python" not in overview
    assert "JavaScript" not in overview


def test_overview_does_not_exceed_four_sentences():
    """Even with all fields populated, the overview stays at most 4 sentences."""
    analysis = RepoAnalysis(
        project_name="big-app",
        languages=["Python", "TypeScript"],
        frameworks=["FastAPI", "React"],
        project_structure={"backend": [], "frontend": [], "tests": []},
        dependencies=[DependencyEntry(name="fastapi"), DependencyEntry(name="react")],
    )
    overview = _fallback_overview(analysis)
    # Count sentences by terminal punctuation (rough but reliable for our output)
    sentence_count = overview.count(".")
    assert sentence_count <= 4, f"Expected ≤4 sentences, got {sentence_count}: {overview!r}"


def test_overview_only_mentions_known_names():
    """Overview must not reference any name absent from the input."""
    analysis = RepoAnalysis(
        project_name="strict-app",
        languages=["Go"],
        frameworks=["Gin"],
        dependencies=[DependencyEntry(name="gin")],
    )
    overview = _fallback_overview(analysis)
    # These names were not in the input and must never appear
    for invented in ("Django", "React", "fastapi", "Node"):
        assert invented.lower() not in overview.lower(), (
            f"Invented name {invented!r} found in overview: {overview!r}"
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
    """Sparse analysis with no signals must still return the sentinel (non-empty list)."""
    result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    # MOCK_ANALYSIS_SPARSE has no deps, no important_files, no project_structure,
    # so no grounded steps can be built — the sentinel must be returned.
    assert result.development_workflow == ["Not derivable from the provided analysis data."], (
        f"development_workflow was not the sentinel for sparse input: {result.development_workflow}"
    )


# ---------------------------------------------------------------------------
# _fallback_workflow — grounded development workflow steps
# ---------------------------------------------------------------------------

def test_workflow_python_with_uvicorn_produces_uvicorn_start():
    """When uvicorn is a dep and main.py is an entry point, prefer 'uvicorn main:app'."""
    analysis = RepoAnalysis(
        project_name="my-api",
        languages=["Python"],
        dependencies=[DependencyEntry(name="uvicorn"), DependencyEntry(name="fastapi")],
        important_files=[ImportantFileEntry(path="backend/main.py", description="entry point")],
    )
    steps = _fallback_workflow(analysis)
    assert any("uvicorn" in s and "main" in s for s in steps), (
        f"Expected uvicorn start step, got: {steps}"
    )


def test_workflow_python_without_uvicorn_uses_python_command():
    """Without uvicorn in deps, start step uses plain 'python ...'."""
    analysis = RepoAnalysis(
        project_name="my-script",
        languages=["Python"],
        dependencies=[DependencyEntry(name="requests")],
        important_files=[ImportantFileEntry(path="app.py", description="main script")],
    )
    steps = _fallback_workflow(analysis)
    assert any("python" in s.lower() and "app.py" in s for s in steps), (
        f"Expected 'python app.py' start step, got: {steps}"
    )


def test_workflow_env_example_triggers_copy_step():
    """A .env.example file must produce a 'copy to .env' step."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Python"],
        important_files=[
            ImportantFileEntry(path=".env.example", description="env template"),
            ImportantFileEntry(path="main.py", description="entry point"),
        ],
    )
    steps = _fallback_workflow(analysis)
    assert any(".env" in s and ("copy" in s.lower() or "Copy" in s) for s in steps), (
        f"Expected env-copy step, got: {steps}"
    )


def test_workflow_config_yaml_triggers_configure_step():
    """A config.yaml file that is not an 'example' must produce a 'review/configure' step."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Go"],
        important_files=[ImportantFileEntry(path="config.yaml", description="app config")],
        project_structure=["main.go", "config.yaml"],
    )
    steps = _fallback_workflow(analysis)
    assert any("config.yaml" in s for s in steps), (
        f"Expected config.yaml configure step, got: {steps}"
    )


def test_workflow_test_dir_triggers_pytest_for_python():
    """A 'tests/' directory in project_structure triggers a pytest step for Python."""
    analysis = RepoAnalysis(
        project_name="my-app",
        languages=["Python"],
        dependencies=[DependencyEntry(name="pytest")],
        project_structure=["src/main.py", "tests/test_main.py"],
    )
    steps = _fallback_workflow(analysis)
    assert any("pytest" in s for s in steps), (
        f"Expected pytest step, got: {steps}"
    )


def test_workflow_test_dir_triggers_go_test():
    """A test file in project_structure triggers 'go test' for Go projects."""
    analysis = RepoAnalysis(
        project_name="my-service",
        languages=["Go"],
        project_structure=["main.go", "handler_test.go"],
    )
    steps = _fallback_workflow(analysis)
    assert any("go test" in s for s in steps), (
        f"Expected go test step, got: {steps}"
    )


def test_workflow_frontend_only_produces_npm_dev():
    """A pure frontend project (React, package.json, no backend) gets 'npm run dev'."""
    analysis = RepoAnalysis(
        project_name="my-ui",
        languages=["TypeScript"],
        frameworks=["React"],
        dependencies=[DependencyEntry(name="react"), DependencyEntry(name="vite")],
    )
    steps = _fallback_workflow(analysis)
    assert any("npm" in s for s in steps), (
        f"Expected npm run dev step for frontend project, got: {steps}"
    )


def test_workflow_fullstack_has_both_backend_and_frontend_steps():
    """Full-stack project (Python backend + React frontend) gets both start steps."""
    analysis = RepoAnalysis(
        project_name="my-fullstack",
        languages=["Python", "TypeScript"],
        frameworks=["FastAPI", "React"],
        dependencies=[
            DependencyEntry(name="fastapi"),
            DependencyEntry(name="uvicorn"),
            DependencyEntry(name="react"),
        ],
        important_files=[
            ImportantFileEntry(path="backend/main.py", description="FastAPI entry point"),
            ImportantFileEntry(path="frontend/package.json", description="frontend deps"),
        ],
    )
    steps = _fallback_workflow(analysis)
    has_backend = any("uvicorn" in s or "python" in s.lower() for s in steps)
    has_frontend = any("npm" in s for s in steps)
    assert has_backend, f"Expected backend start step, got: {steps}"
    assert has_frontend, f"Expected frontend start step, got: {steps}"


def test_workflow_produces_non_empty_list():
    """_fallback_workflow must always return a non-empty list."""
    for analysis in (MOCK_ANALYSIS_COMPLETE, MOCK_ANALYSIS_SPARSE):
        steps = _fallback_workflow(analysis)
        assert isinstance(steps, list) and len(steps) >= 1, (
            f"Expected non-empty list, got: {steps}"
        )


def test_workflow_complete_mock_produces_real_steps():
    """MOCK_ANALYSIS_COMPLETE has enough signals for at least 2 grounded steps."""
    steps = _fallback_workflow(MOCK_ANALYSIS_COMPLETE)
    assert len(steps) >= 2, f"Expected ≥2 steps from complete mock, got: {steps}"
    assert steps != ["Not derivable from the provided analysis data."], (
        f"Should not fall back to sentinel for complete input: {steps}"
    )


def test_normalised_paths_includes_important_files_and_structure():
    """_normalised_paths must include entries from both important_files and project_structure."""
    analysis = RepoAnalysis(
        project_name="x",
        important_files=[ImportantFileEntry(path="Backend/Main.py", description="")],
        project_structure=["src/App.ts", "tests/test_app.py"],
    )
    paths = _normalised_paths(analysis)
    assert "backend/main.py" in paths
    assert "src/app.ts" in paths
    assert "tests/test_app.py" in paths


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
    test_workflow_python_with_uvicorn_produces_uvicorn_start()
    test_workflow_python_without_uvicorn_uses_python_command()
    test_workflow_env_example_triggers_copy_step()
    test_workflow_config_yaml_triggers_configure_step()
    test_workflow_test_dir_triggers_pytest_for_python()
    test_workflow_test_dir_triggers_go_test()
    test_workflow_frontend_only_produces_npm_dev()
    test_workflow_fullstack_has_both_backend_and_frontend_steps()
    test_workflow_produces_non_empty_list()
    test_workflow_complete_mock_produces_real_steps()
    test_normalised_paths_includes_important_files_and_structure()
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
