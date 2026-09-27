"""
Integration tests for POST /analyze.

These tests exercise the full backend pipeline:
    URL validation → git clone → analyze_repository() → to_repo_analysis()
    → RepoAnalysis → generate_onboarding()

All tests run offline (no real network calls, no real git clones).
- Clone is always mocked via ``patch("backend.main._clone_repository")``.
- ``analyze_repository`` is mocked where the test is not exercising that layer.
- ``use_llm`` is implicitly False because no ANTHROPIC_API_KEY is set in the
  test environment, so the rule-based fallback path is used.

Run with:
    cd <project-root>
    backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v
"""

import contextlib
import shutil
import sys
import os
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the project root is importable (same guard as main.py)
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from fastapi.testclient import TestClient

from backend.main import app, _validate_repo_url, _clone_repository

client = TestClient(app)

# A valid URL used throughout the tests (never actually contacted).
_VALID_URL = "https://github.com/example/repo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_analyze(repo_url: str) -> "httpx.Response":  # type: ignore[name-defined]
    return client.post("/analyze", json={"repo_url": repo_url})


def _make_analyzer_ok_result(path: str | None = None) -> dict:
    """Return a minimal well-formed analyzer result dict."""
    return {
        "status": "ok",
        "repo_path": path or str(_project_root),
        "total_files": 5,
        "total_dirs": 2,
        "languages": {"Python": 3},
        "important_files": {"backend/main.py": "FastAPI entry point"},
        "readme": {"title": "Test Project"},
        "structure": {
            "type": "Python application",
            "has_tests": True,
            "has_ci": False,
            "has_docker": False,
            "top_level_dirs": ["backend"],
            "entry_points": ["backend/main.py"],
        },
        "dependencies": [
            {"source": "requirements.txt", "packages": ["fastapi", "pydantic"]}
        ],
    }


@contextlib.contextmanager
def _mock_clone_ok(tmpdir_to_use: str):
    """Context manager that mocks _clone_repository to return *tmpdir_to_use*.

    Also patches ``shutil.rmtree`` in ``backend.main`` so that if
    *tmpdir_to_use* is a real directory we don't want deleted (e.g. the project
    root used for full-pipeline tests), the ``finally`` cleanup block does not
    remove it.  Tests that explicitly verify cleanup behaviour use their own
    ``tempfile.mkdtemp()`` directories and do NOT use this helper.
    """
    with ExitStack() as stack:
        stack.enter_context(
            patch("backend.main._clone_repository", return_value=tmpdir_to_use)
        )
        stack.enter_context(
            patch("backend.main.shutil.rmtree")  # prevent cleanup of the real path
        )
        yield


# ---------------------------------------------------------------------------
# 1. URL validation (unit — no clone, no network)
# ---------------------------------------------------------------------------

class TestURLValidation:
    """_validate_repo_url() and the Pydantic validator on AnalyzeRequest."""

    # --- pure helper unit tests ---

    def test_blank_url_raises(self):
        with pytest.raises(ValueError, match="blank"):
            _validate_repo_url("   ")

    def test_http_not_allowed(self):
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_repo_url("http://github.com/org/repo")

    def test_ssh_url_not_allowed(self):
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_repo_url("git@github.com:org/repo.git")

    def test_file_url_not_allowed(self):
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_repo_url("file:///tmp/myrepo")

    def test_unsupported_host_not_allowed(self):
        with pytest.raises(ValueError, match="GitHub, GitLab, or Bitbucket"):
            _validate_repo_url("https://example.com/org/repo")

    def test_credentials_in_url_not_allowed(self):
        with pytest.raises(ValueError, match="GitHub, GitLab, or Bitbucket"):
            _validate_repo_url("https://token@github.com/org/repo")

    def test_github_url_accepted(self):
        assert _validate_repo_url("https://github.com/org/repo") == "https://github.com/org/repo"

    def test_gitlab_url_accepted(self):
        assert _validate_repo_url("https://gitlab.com/org/repo") == "https://gitlab.com/org/repo"

    def test_bitbucket_url_accepted(self):
        assert _validate_repo_url("https://bitbucket.org/org/repo") == "https://bitbucket.org/org/repo"

    def test_strips_surrounding_whitespace(self):
        result = _validate_repo_url("  https://github.com/org/repo  ")
        assert result == "https://github.com/org/repo"

    # --- via HTTP endpoint (Pydantic validator) ---

    def test_blank_url_returns_422_via_endpoint(self):
        resp = client.post("/analyze", json={"repo_url": "   "})
        assert resp.status_code == 422

    def test_http_url_returns_422_via_endpoint(self):
        resp = client.post("/analyze", json={"repo_url": "http://github.com/org/repo"})
        assert resp.status_code == 422

    def test_unsupported_host_returns_422_via_endpoint(self):
        resp = client.post("/analyze", json={"repo_url": "https://example.com/org/repo"})
        assert resp.status_code == 422

    def test_missing_repo_url_field_returns_422(self):
        resp = client.post("/analyze", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 2. Clone failure (mock subprocess — no network)
# ---------------------------------------------------------------------------

class TestCloneFailure:
    """_clone_repository() error paths, exercised via the endpoint."""

    def test_git_not_found_returns_500(self):
        with patch("backend.main.subprocess.run", side_effect=FileNotFoundError()):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 500
        assert "git" in resp.json()["detail"].lower()

    def test_clone_nonzero_exit_returns_400(self):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: repository 'https://github.com/example/repo/' not found"
        with patch("backend.main.subprocess.run", return_value=mock_result):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 400
        assert "Could not clone repository" in resp.json()["detail"]

    def test_clone_nonzero_empty_stderr_returns_400(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = ""
        with patch("backend.main.subprocess.run", return_value=mock_result):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Could not clone repository"

    def test_clone_timeout_returns_400(self):
        import subprocess as _sp
        with patch("backend.main.subprocess.run", side_effect=_sp.TimeoutExpired(cmd="git", timeout=120)):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 400
        assert "timed out" in resp.json()["detail"].lower()

    def test_clone_error_detail_is_string(self):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "some error"
        with patch("backend.main.subprocess.run", return_value=mock_result):
            resp = _post_analyze(_VALID_URL)
        assert isinstance(resp.json()["detail"], str)

    def test_stderr_truncated_to_300_chars(self):
        long_stderr = "x" * 500
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = long_stderr
        with patch("backend.main.subprocess.run", return_value=mock_result):
            resp = _post_analyze(_VALID_URL)
        # 300 chars of stderr + "Could not clone repository: " prefix
        detail = resp.json()["detail"]
        assert len(detail) <= len("Could not clone repository: ") + 300


# ---------------------------------------------------------------------------
# 3. Successful clone → analyzer → adapter → AI flow
# ---------------------------------------------------------------------------

class TestValidRepository:
    """POST /analyze with a mocked successful clone pointing at the project root."""

    def test_returns_200(self):
        with _mock_clone_ok(str(_project_root)):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 200, resp.text

    def test_response_has_onboarding_knowledge_fields(self):
        with _mock_clone_ok(str(_project_root)):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 200
        data = resp.json()
        for field in (
            "project_overview",
            "tech_stack",
            "architecture",
            "important_files",
            "dependencies",
            "setup_guide",
            "development_workflow",
            "starter_tasks",
            "architecture_diagram",
            "used_llm",
            "data_completeness_notes",
        ):
            assert field in data, f"Missing field: {field}"

    def test_used_llm_is_false_without_api_key(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with _mock_clone_ok(str(_project_root)), patch.dict(os.environ, env, clear=True):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 200
        assert resp.json()["used_llm"] is False

    def test_tech_stack_contains_python(self):
        with _mock_clone_ok(str(_project_root)):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()["tech_stack"]]
        assert "Python" in names

    def test_architecture_diagram_is_mermaid_string(self):
        with _mock_clone_ok(str(_project_root)):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 200
        diagram = resp.json()["architecture_diagram"]
        assert isinstance(diagram, str)
        assert len(diagram) > 0


# ---------------------------------------------------------------------------
# 4. Analyzer error handling
# ---------------------------------------------------------------------------

class TestAnalyzerError:
    """POST /analyze when analyze_repository() returns status=="error"."""

    def test_analyzer_error_returns_400(self):
        with _mock_clone_ok(str(_project_root)), \
             patch("backend.main.analyze_repository") as mock_ar:
            mock_ar.return_value = {
                "status": "error",
                "error": "Simulated analyzer failure",
                "repo_path": "/fake",
            }
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Simulated analyzer failure"

    def test_analyzer_error_without_message_still_400(self):
        with _mock_clone_ok(str(_project_root)), \
             patch("backend.main.analyze_repository") as mock_ar:
            mock_ar.return_value = {"status": "error", "repo_path": "/fake"}
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 400
        assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# 5. Temporary-directory cleanup
# ---------------------------------------------------------------------------

class TestTempDirCleanup:
    """The temporary clone directory must always be removed.

    These tests use real ``tempfile.mkdtemp()`` directories and do NOT use
    ``_mock_clone_ok`` so that the actual ``shutil.rmtree`` call in the
    ``finally`` block is exercised.
    """

    def test_tmpdir_removed_after_successful_analysis(self):
        """After a 200, the directory created by _clone_repository must not exist."""
        real_tmpdir = tempfile.mkdtemp(prefix="test_onboarding_")
        try:
            with patch("backend.main._clone_repository", return_value=real_tmpdir), \
                 patch("backend.main.analyze_repository", return_value=_make_analyzer_ok_result(real_tmpdir)):
                resp = _post_analyze(_VALID_URL)
            assert resp.status_code == 200
            assert not os.path.exists(real_tmpdir), "Temp dir was not cleaned up after success"
        finally:
            shutil.rmtree(real_tmpdir, ignore_errors=True)

    def test_tmpdir_removed_after_analyzer_error(self):
        """After a 400 from the analyzer, the temp dir must also be removed."""
        real_tmpdir = tempfile.mkdtemp(prefix="test_onboarding_")
        try:
            with patch("backend.main._clone_repository", return_value=real_tmpdir), \
                 patch("backend.main.analyze_repository") as mock_ar:
                mock_ar.return_value = {"status": "error", "error": "boom", "repo_path": real_tmpdir}
                resp = _post_analyze(_VALID_URL)
            assert resp.status_code == 400
            assert not os.path.exists(real_tmpdir), "Temp dir was not cleaned up after analyzer error"
        finally:
            shutil.rmtree(real_tmpdir, ignore_errors=True)

    def test_tmpdir_removed_after_ai_error(self):
        """After a 500 from the AI layer, the temp dir must also be removed."""
        real_tmpdir = tempfile.mkdtemp(prefix="test_onboarding_")
        try:
            with patch("backend.main._clone_repository", return_value=real_tmpdir), \
                 patch("backend.main.analyze_repository", return_value=_make_analyzer_ok_result(real_tmpdir)), \
                 patch("backend.main.generate_onboarding", side_effect=RuntimeError("AI exploded")):
                resp = _post_analyze(_VALID_URL)
            assert resp.status_code == 500
            assert not os.path.exists(real_tmpdir), "Temp dir was not cleaned up after AI error"
        finally:
            shutil.rmtree(real_tmpdir, ignore_errors=True)

    def test_analyze_repository_called_with_tmpdir_not_url(self):
        """analyze_repository must receive the local clone path, not the URL."""
        real_tmpdir = tempfile.mkdtemp(prefix="test_onboarding_")
        try:
            with patch("backend.main._clone_repository", return_value=real_tmpdir), \
                 patch("backend.main.analyze_repository", return_value=_make_analyzer_ok_result(real_tmpdir)) as mock_ar:
                _post_analyze(_VALID_URL)
            called_with = mock_ar.call_args[0][0]
            assert called_with == real_tmpdir
            assert called_with != _VALID_URL
        finally:
            shutil.rmtree(real_tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 6. Adapter → AI layer wiring
# ---------------------------------------------------------------------------

class TestAdapterToAIFlow:
    """Verify the adapter + AI layer are wired together correctly."""

    def test_to_repo_analysis_is_called_with_analyzer_output(self):
        """The adapter must be called with the analyzer's result dict."""
        real_result = _make_analyzer_ok_result()
        with _mock_clone_ok(str(_project_root)), \
             patch("backend.main.analyze_repository", return_value=real_result) as mock_ar, \
             patch("backend.main.to_repo_analysis", wraps=__import__(
                 "backend.analyzer_adapter", fromlist=["to_repo_analysis"]
             ).to_repo_analysis) as mock_adapter:
            resp = _post_analyze(_VALID_URL)

        assert resp.status_code == 200
        mock_adapter.assert_called_once_with(real_result)

    def test_generate_onboarding_is_called_with_repo_analysis(self):
        """generate_onboarding must receive a RepoAnalysis instance."""
        from ai.schemas import OnboardingKnowledge, TechStackItem

        fake_knowledge = OnboardingKnowledge(
            project_overview="Test project",
            tech_stack=[TechStackItem(name="Python", category="language", role="Used in project.")],
            architecture="Monolith",
            important_files=[],
            dependencies=[],
            setup_guide=["Install deps"],
            development_workflow=["Run tests"],
            starter_tasks=["Read README"],
            architecture_diagram="graph TD\n    A --> B",
            used_llm=False,
            data_completeness_notes=[],
        )

        with _mock_clone_ok(str(_project_root)), \
             patch("backend.main.generate_onboarding", return_value=fake_knowledge) as mock_gen:
            resp = _post_analyze(_VALID_URL)

        assert resp.status_code == 200
        mock_gen.assert_called_once()
        call_args = mock_gen.call_args
        from ai.schemas import RepoAnalysis
        assert isinstance(call_args[0][0], RepoAnalysis)

    def test_response_matches_onboarding_knowledge_schema(self):
        """The JSON response must be parseable as an OnboardingKnowledge instance."""
        from ai.schemas import OnboardingKnowledge
        with _mock_clone_ok(str(_project_root)):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 200
        knowledge = OnboardingKnowledge.model_validate(resp.json())
        assert knowledge.project_overview


# ---------------------------------------------------------------------------
# 7. AI fallback behavior
# ---------------------------------------------------------------------------

class TestAIFallbackBehavior:
    """Verify the fallback path is used and produces correct output."""

    def test_fallback_used_when_no_api_key(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with _mock_clone_ok(str(_project_root)), patch.dict(os.environ, env, clear=True):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 200
        assert resp.json()["used_llm"] is False

    def test_fallback_output_has_data_completeness_notes(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with _mock_clone_ok(str(_project_root)), patch.dict(os.environ, env, clear=True):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 200
        notes = resp.json()["data_completeness_notes"]
        assert any("architecture" in note for note in notes)

    def test_fallback_when_llm_path_raises(self):
        with _mock_clone_ok(str(_project_root)), \
             patch("ai.generator._llm_generate", side_effect=RuntimeError("LLM exploded")):
            resp = _post_analyze(_VALID_URL)
        assert resp.status_code == 200
        assert resp.json()["used_llm"] is False


# ---------------------------------------------------------------------------
# 8. CORS preflight
# ---------------------------------------------------------------------------

class TestCORSPreflight:
    """OPTIONS /analyze must return the correct CORS headers."""

    def test_options_analyze_returns_200(self):
        resp = client.options(
            "/analyze",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert resp.status_code == 200

    def test_options_analyze_allows_post(self):
        resp = client.options(
            "/analyze",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        allowed = resp.headers.get("access-control-allow-methods", "")
        assert "POST" in allowed

    def test_options_analyze_allows_localhost_5173(self):
        resp = client.options(
            "/analyze",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_options_analyze_allows_127_0_0_1_5173(self):
        resp = client.options(
            "/analyze",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"

    def test_unknown_origin_not_echoed(self):
        resp = client.options(
            "/analyze",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "http://evil.example.com"


# ---------------------------------------------------------------------------
# 9. Preserved endpoints
# ---------------------------------------------------------------------------

class TestPreservedEndpoints:
    """Root and /health must still work after contract change."""

    def test_root_returns_200(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "running" in resp.json()["message"]

    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
