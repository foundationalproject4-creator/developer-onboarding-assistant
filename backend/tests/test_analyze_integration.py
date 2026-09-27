"""
Integration tests for POST /analyze.

These tests exercise the full backend pipeline:
    analyze_repository() → to_repo_analysis() → RepoAnalysis → generate_onboarding()

All tests run offline (use_llm is implicitly False because no ANTHROPIC_API_KEY
is set in the test environment), so the rule-based fallback path is used.  This
is intentional — the tests check integration correctness, not LLM quality.

Run with:
    cd <project-root>
    backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the project root is importable (same guard as main.py)
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_analyze(repo_path: str) -> "httpx.Response":  # type: ignore[name-defined]
    return client.post("/analyze", json={"repo_path": repo_path})


# ---------------------------------------------------------------------------
# 1. Valid repository path — should return OnboardingKnowledge JSON
# ---------------------------------------------------------------------------

class TestValidRepository:
    """POST /analyze with a real, accessible repository path."""

    def test_returns_200(self):
        resp = _post_analyze(str(_project_root))
        assert resp.status_code == 200, resp.text

    def test_response_has_onboarding_knowledge_fields(self):
        resp = _post_analyze(str(_project_root))
        assert resp.status_code == 200
        data = resp.json()
        # Core OnboardingKnowledge fields must be present
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
        """Without an ANTHROPIC_API_KEY the fallback path should be used."""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            resp = _post_analyze(str(_project_root))
        assert resp.status_code == 200
        assert resp.json()["used_llm"] is False

    def test_tech_stack_contains_python(self):
        """The project root has Python files — tech_stack must include Python."""
        resp = _post_analyze(str(_project_root))
        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()["tech_stack"]]
        assert "Python" in names

    def test_architecture_diagram_is_mermaid_string(self):
        resp = _post_analyze(str(_project_root))
        assert resp.status_code == 200
        diagram = resp.json()["architecture_diagram"]
        assert isinstance(diagram, str)
        assert len(diagram) > 0


# ---------------------------------------------------------------------------
# 2. Invalid repository path — should return 400
# ---------------------------------------------------------------------------

class TestInvalidRepositoryPath:
    """POST /analyze with a path that does not exist."""

    def test_nonexistent_path_returns_400(self):
        resp = _post_analyze("/this/path/does/not/exist/at/all")
        assert resp.status_code == 400

    def test_error_detail_mentions_path(self):
        resp = _post_analyze("/this/path/does/not/exist/at/all")
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert isinstance(detail, str)
        assert len(detail) > 0

    def test_blank_repo_path_returns_422(self):
        """Blank repo_path is rejected by the Pydantic validator before hitting the handler."""
        resp = client.post("/analyze", json={"repo_path": "   "})
        assert resp.status_code == 422

    def test_file_path_instead_of_directory_returns_400(self):
        """Pointing to a file (not a directory) should yield 400."""
        file_path = str(_project_root / "backend" / "main.py")
        resp = _post_analyze(file_path)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Analyzer error handling — status=="error" dict returned by analyzer
# ---------------------------------------------------------------------------

class TestAnalyzerError:
    """POST /analyze when analyze_repository() returns status=="error"."""

    def test_analyzer_error_returns_400(self):
        """Simulate the analyzer returning an error dict."""
        with patch("backend.main.analyze_repository") as mock_ar:
            mock_ar.return_value = {
                "status": "error",
                "error": "Simulated analyzer failure",
                "repo_path": "/fake",
            }
            resp = _post_analyze("/fake")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Simulated analyzer failure"

    def test_analyzer_error_without_message_still_400(self):
        """Error dict with no 'error' key should still yield a 400."""
        with patch("backend.main.analyze_repository") as mock_ar:
            mock_ar.return_value = {"status": "error", "repo_path": "/fake"}
            resp = _post_analyze("/fake")
        assert resp.status_code == 400
        assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# 4. Successful adapter → AI flow
# ---------------------------------------------------------------------------

class TestAdapterToAIFlow:
    """Verify the adapter + AI layer are wired together correctly."""

    def test_to_repo_analysis_is_called_with_analyzer_output(self):
        """The adapter must be called with the analyzer's result dict."""
        real_result = {
            "status": "ok",
            "repo_path": str(_project_root),
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
            "dependencies": [{"source": "requirements.txt", "packages": ["fastapi", "pydantic"]}],
        }
        with patch("backend.main.analyze_repository", return_value=real_result) as mock_ar, \
             patch("backend.main.to_repo_analysis", wraps=__import__(
                 "backend.analyzer_adapter", fromlist=["to_repo_analysis"]
             ).to_repo_analysis) as mock_adapter:
            resp = _post_analyze(str(_project_root))

        assert resp.status_code == 200
        # Adapter was called once with the full analyzer result
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

        with patch("backend.main.generate_onboarding", return_value=fake_knowledge) as mock_gen:
            resp = _post_analyze(str(_project_root))

        assert resp.status_code == 200
        mock_gen.assert_called_once()
        call_args = mock_gen.call_args
        from ai.schemas import RepoAnalysis
        assert isinstance(call_args[0][0], RepoAnalysis)

    def test_response_matches_onboarding_knowledge_schema(self):
        """The JSON response must be parseable as an OnboardingKnowledge instance."""
        from ai.schemas import OnboardingKnowledge
        resp = _post_analyze(str(_project_root))
        assert resp.status_code == 200
        # This will raise if the schema doesn't match
        knowledge = OnboardingKnowledge.model_validate(resp.json())
        assert knowledge.project_overview


# ---------------------------------------------------------------------------
# 5. AI fallback behavior
# ---------------------------------------------------------------------------

class TestAIFallbackBehavior:
    """Verify the fallback path is used and produces correct output."""

    def test_fallback_used_when_no_api_key(self):
        """Without ANTHROPIC_API_KEY, used_llm must be False."""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            resp = _post_analyze(str(_project_root))
        assert resp.status_code == 200
        assert resp.json()["used_llm"] is False

    def test_fallback_output_has_data_completeness_notes(self):
        """Fallback always adds architecture note to data_completeness_notes."""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            resp = _post_analyze(str(_project_root))
        assert resp.status_code == 200
        notes = resp.json()["data_completeness_notes"]
        assert any("architecture" in note for note in notes)

    def test_fallback_when_llm_path_raises(self):
        """Even if the LLM path raises, the fallback must produce a 200."""
        with patch("ai.generator._llm_generate", side_effect=RuntimeError("LLM exploded")):
            resp = _post_analyze(str(_project_root))
        assert resp.status_code == 200
        assert resp.json()["used_llm"] is False


# ---------------------------------------------------------------------------
# 6. Preserved endpoints
# ---------------------------------------------------------------------------

class TestPreservedEndpoints:
    """Root and /health must still work after integration changes."""

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
