"""
Tests for ai/sanitize.py and ai/generator.py budget cap.

Covers:
- sanitize_analysis() correctly redacts API keys, tokens, PEM headers,
  connection strings, .env-style assignments in all RepoAnalysis fields.
- sanitize_analysis() redacts known secret-bearing filenames.
- sanitize_analysis() does NOT redact clean, normal values.
- Redacted values never appear in the SanitizeResult.redactions list
  (only field path + pattern name are recorded).
- Budget cap: AI_MAX_REQUESTS env var short-circuits to fallback after N calls.
- Budget cap resets on module-level state reset.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from ai.sanitize import (
    REDACTED,
    SanitizeResult,
    _is_secret_filename,
    _is_secret_value,
    sanitize_analysis,
)
from ai.schemas import DependencyEntry, ImportantFileEntry, RepoAnalysis
from ai.generator import _cache, generate_onboarding, async_generate_onboarding
import ai.generator as gen_module


# ---------------------------------------------------------------------------
# _is_secret_value unit tests
# ---------------------------------------------------------------------------

def test_anthropic_api_key_detected():
    matched, pattern = _is_secret_value("sk-ant-api03-A" + "B" * 50)
    assert matched
    assert "anthropic" in pattern


def test_openai_api_key_detected():
    matched, pattern = _is_secret_value("sk-" + "A" * 48)
    assert matched
    assert "openai" in pattern or "anthropic" in pattern  # either is fine


def test_aws_access_key_detected():
    matched, pattern = _is_secret_value("AKIAIOSFODNN7EXAMPLE")
    assert matched
    assert "aws" in pattern


def test_github_token_detected():
    matched, pattern = _is_secret_value("ghp_" + "A" * 36)
    assert matched
    assert "github" in pattern


def test_pem_header_detected():
    matched, pattern = _is_secret_value("-----BEGIN RSA PRIVATE KEY-----")
    assert matched
    assert "pem" in pattern


def test_connection_string_with_password_detected():
    matched, pattern = _is_secret_value("postgresql://user:supersecretpassword@localhost/db")
    assert matched
    assert "connection" in pattern


def test_dotenv_assignment_detected():
    matched, pattern = _is_secret_value("API_SECRET=verylongsecretvalue12345678")
    assert matched
    assert "dotenv" in pattern


def test_normal_string_not_flagged():
    matched, _ = _is_secret_value("FastAPI")
    assert not matched


def test_short_string_not_flagged():
    matched, _ = _is_secret_value("sk-short")
    assert not matched


def test_dep_name_not_flagged():
    matched, _ = _is_secret_value("anthropic")
    assert not matched


# ---------------------------------------------------------------------------
# _is_secret_filename unit tests
# ---------------------------------------------------------------------------

def test_dotenv_file_detected():
    matched, pattern = _is_secret_filename(".env")
    assert matched
    assert "dotenv" in pattern


def test_dotenv_local_file_detected():
    matched, pattern = _is_secret_filename(".env.local")
    assert matched


def test_pem_file_detected():
    matched, pattern = _is_secret_filename("server.pem")
    assert matched


def test_id_rsa_detected():
    matched, pattern = _is_secret_filename("id_rsa")
    assert matched


def test_credentials_json_detected():
    matched, pattern = _is_secret_filename("credentials.json")
    assert matched


def test_service_account_json_detected():
    matched, pattern = _is_secret_filename("service-account.json")
    assert matched


def test_requirements_txt_not_flagged():
    matched, _ = _is_secret_filename("requirements.txt")
    assert not matched


def test_main_py_not_flagged():
    matched, _ = _is_secret_filename("main.py")
    assert not matched


def test_src_key_generator_py_not_flagged():
    """A file *named* keygen.py in a src/ directory must not be flagged."""
    matched, _ = _is_secret_filename("keygen.py")
    assert not matched


# ---------------------------------------------------------------------------
# sanitize_analysis integration tests
# ---------------------------------------------------------------------------

def _make_clean_analysis() -> RepoAnalysis:
    return RepoAnalysis(
        project_name="my-app",
        languages=["Python"],
        frameworks=["FastAPI"],
        important_files=[
            ImportantFileEntry(path="main.py", description="Entry point"),
        ],
        dependencies=[DependencyEntry(name="fastapi", version="0.115.0")],
    )


def test_clean_analysis_unchanged():
    """A normal analysis with no secrets must pass through unchanged."""
    analysis = _make_clean_analysis()
    result = sanitize_analysis(analysis)
    assert not result.had_redactions
    assert result.analysis.project_name == "my-app"
    assert result.analysis.dependencies[0].name == "fastapi"


def test_api_key_in_description_is_redacted():
    analysis = RepoAnalysis(
        project_name="x",
        important_files=[
            ImportantFileEntry(
                path="config.py",
                description="AKIAIOSFODNN7EXAMPLE",  # AWS key in description
            )
        ],
    )
    result = sanitize_analysis(analysis)
    assert result.had_redactions
    assert result.analysis.important_files[0].description == REDACTED
    # The actual key value must NOT appear in the redactions list
    for r in result.redactions:
        assert "AKIAIOSFODNN7EXAMPLE" not in r


def test_secret_filename_is_redacted():
    analysis = RepoAnalysis(
        project_name="x",
        important_files=[ImportantFileEntry(path=".env", description="Env vars")],
    )
    result = sanitize_analysis(analysis)
    assert result.had_redactions
    # Both path and description should be redacted when the filename is secret
    assert result.analysis.important_files[0].path == REDACTED


def test_pem_key_in_dep_version_redacted():
    analysis = RepoAnalysis(
        project_name="x",
        dependencies=[
            DependencyEntry(
                name="mylib",
                version="-----BEGIN RSA PRIVATE KEY-----",
            )
        ],
    )
    result = sanitize_analysis(analysis)
    assert result.had_redactions
    assert result.analysis.dependencies[0].version == REDACTED


def test_secret_in_project_structure_redacted():
    analysis = RepoAnalysis(
        project_name="x",
        project_structure={"secrets": [".env", "id_rsa", "main.py"]},
    )
    result = sanitize_analysis(analysis)
    assert result.had_redactions
    # .env and id_rsa should be redacted; main.py should survive
    struct = result.analysis.project_structure["secrets"]
    assert struct[0] == REDACTED   # .env
    assert struct[1] == REDACTED   # id_rsa
    assert struct[2] == "main.py"  # clean


def test_redaction_list_never_contains_secret_value(caplog):
    """The redactions list and log output must not contain the raw secret value."""
    import logging
    key = "sk-ant-api03-" + "X" * 50
    analysis = RepoAnalysis(
        project_name="x",
        important_files=[ImportantFileEntry(path="config.py", description=key)],
    )
    with caplog.at_level(logging.WARNING, logger="ai.sanitize"):
        result = sanitize_analysis(analysis)
    # The full key must not appear in the redactions metadata
    for r in result.redactions:
        assert key not in r
    # The full key must not appear in log messages
    for record in caplog.records:
        assert key not in record.message


def test_sanitize_result_had_redactions_false_when_clean():
    result = sanitize_analysis(_make_clean_analysis())
    assert result.had_redactions is False


def test_sanitize_result_had_redactions_true_when_secret():
    analysis = RepoAnalysis(
        project_name="x",
        important_files=[ImportantFileEntry(path=".env")],
    )
    result = sanitize_analysis(analysis)
    assert result.had_redactions is True


# ---------------------------------------------------------------------------
# Sanitize is called on the LLM path (integration)
# ---------------------------------------------------------------------------

def _make_llm_result():
    return {
        "project_overview": "Test",
        "tech_stack": [],
        "architecture": "Test arch",
        "important_files": [],
        "dependencies": [],
        "setup_guide": ["run tests"],
        "development_workflow": ["push"],
        "starter_tasks": ["read code"],
        "data_completeness_notes": [],
        "architecture_diagram": "graph TD\n    B[\"Backend\"]",
        "used_llm": True,
    }


def test_sanitize_called_on_llm_path(caplog):
    """When a secret-bearing filename is in important_files, a sanitize warning is logged."""
    import logging
    _cache.clear()
    analysis = RepoAnalysis(
        project_name="x",
        languages=["Python"],
        frameworks=["FastAPI"],
        important_files=[ImportantFileEntry(path=".env", description="secrets")],
        dependencies=[DependencyEntry(name="fastapi")],
    )
    with patch("ai.generator.call_llm", return_value=_make_llm_result()):
        with caplog.at_level(logging.WARNING, logger="ai.generator"):
            result = generate_onboarding(analysis, use_llm=True)
    assert result.used_llm is True
    assert any("sanitize" in r.message for r in caplog.records), (
        f"Expected sanitize warning in logs; got: {[r.message for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# Budget cap tests
# ---------------------------------------------------------------------------

def _reset_budget():
    """Reset the module-level call counter between tests."""
    gen_module._budget_llm_calls = 0


def test_budget_cap_zero_means_unlimited():
    """AI_MAX_REQUESTS=0 must never block a call."""
    _reset_budget()
    os.environ["AI_MAX_REQUESTS"] = "0"
    try:
        _cache.clear()
        with patch("ai.generator.call_llm", return_value=_make_llm_result()) as mock:
            for _ in range(5):
                generate_onboarding(
                    RepoAnalysis(project_name=f"p{_}", languages=["Python"], frameworks=["FastAPI"]),
                    use_llm=True,
                )
        assert mock.call_count == 5
    finally:
        del os.environ["AI_MAX_REQUESTS"]
        _reset_budget()


def test_budget_cap_blocks_after_limit(caplog):
    """AI_MAX_REQUESTS=2 must block the 3rd call and return fallback."""
    import logging
    _reset_budget()
    _cache.clear()
    os.environ["AI_MAX_REQUESTS"] = "2"
    try:
        call_count = 0

        def _fake_llm(sys_p, usr_p):
            nonlocal call_count
            call_count += 1
            return _make_llm_result()

        with caplog.at_level(logging.WARNING, logger="ai.generator"):
            with patch("ai.generator.call_llm", side_effect=_fake_llm):
                r1 = generate_onboarding(
                    RepoAnalysis(project_name="p1", languages=["Python"], frameworks=["FastAPI"]),
                    use_llm=True,
                )
                r2 = generate_onboarding(
                    RepoAnalysis(project_name="p2", languages=["Python"], frameworks=["FastAPI"]),
                    use_llm=True,
                )
                r3 = generate_onboarding(
                    RepoAnalysis(project_name="p3", languages=["Python"], frameworks=["FastAPI"]),
                    use_llm=True,
                )

        assert call_count == 2, f"Expected 2 LLM calls, got {call_count}"
        assert r1.used_llm is True
        assert r2.used_llm is True
        assert r3.used_llm is False   # budget exceeded → fallback
        assert any("budget_cap" in r.message for r in caplog.records), (
            f"Expected budget_cap warning; got: {[r.message for r in caplog.records]}"
        )
    finally:
        del os.environ["AI_MAX_REQUESTS"]
        _reset_budget()


def test_budget_cap_cache_hit_does_not_count():
    """A cache hit does not consume budget — the cap only applies to real LLM calls."""
    _reset_budget()
    _cache.clear()
    os.environ["AI_MAX_REQUESTS"] = "1"
    try:
        call_count = 0
        analysis = RepoAnalysis(project_name="same", languages=["Python"], frameworks=["FastAPI"])

        def _fake_llm(sys_p, usr_p):
            nonlocal call_count
            call_count += 1
            return _make_llm_result()

        with patch("ai.generator.call_llm", side_effect=_fake_llm):
            r1 = generate_onboarding(analysis, use_llm=True)
            r2 = generate_onboarding(analysis, use_llm=True)  # cache hit
            r3 = generate_onboarding(analysis, use_llm=True)  # cache hit

        assert call_count == 1
        assert r1.used_llm is True
        assert r2.used_llm is True  # from cache
        assert r3.used_llm is True  # from cache
    finally:
        del os.environ["AI_MAX_REQUESTS"]
        _reset_budget()


def test_budget_cap_async_path(caplog):
    """Budget cap works on the async entry point too."""
    import logging
    _reset_budget()
    _cache.clear()
    os.environ["AI_MAX_REQUESTS"] = "1"
    try:
        call_count = 0

        async def _run():
            nonlocal call_count

            async def _fake_llm(sys_p, usr_p):
                nonlocal call_count
                call_count += 1
                return _make_llm_result()

            with patch("ai.generator.acall_llm", new_callable=AsyncMock,
                       side_effect=_fake_llm):
                r1 = await async_generate_onboarding(
                    RepoAnalysis(project_name="a1", languages=["Python"], frameworks=["FastAPI"]),
                    use_llm=True,
                )
                r2 = await async_generate_onboarding(
                    RepoAnalysis(project_name="a2", languages=["Python"], frameworks=["FastAPI"]),
                    use_llm=True,
                )
            return r1, r2

        with caplog.at_level(logging.WARNING, logger="ai.generator"):
            r1, r2 = asyncio.run(_run())

        assert call_count == 1
        assert r1.used_llm is True
        assert r2.used_llm is False
    finally:
        del os.environ["AI_MAX_REQUESTS"]
        _reset_budget()
