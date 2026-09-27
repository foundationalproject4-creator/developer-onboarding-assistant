"""
Tests for analyzer/repository_cloner.py.

All tests run offline — no real git clone is performed.
Network-dependent behaviour is tested by mocking subprocess.run.

Run with:
    python analyzer/tests/test_repository_cloner.py
or (if pytest is installed):
    python -m pytest analyzer/tests/test_repository_cloner.py -v
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make sure the project root is on sys.path so the import works from any cwd.
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from analyzer.repository_cloner import (
    CLONE_TIMEOUT_SECONDS,
    analyze_remote_repository,
    is_repo_url,
)


# ---------------------------------------------------------------------------
# URL validation tests
# ---------------------------------------------------------------------------

class TestIsRepoUrl(unittest.TestCase):
    """is_repo_url() must accept valid HTTPS repo URLs and reject everything else."""

    # ── valid URLs ────────────────────────────────────────────────────────────

    def test_github_plain(self):
        self.assertTrue(is_repo_url("https://github.com/owner/repo"))

    def test_github_dot_git_suffix(self):
        self.assertTrue(is_repo_url("https://github.com/owner/repo.git"))

    def test_github_trailing_slash(self):
        self.assertTrue(is_repo_url("https://github.com/owner/repo/"))

    def test_gitlab_plain(self):
        self.assertTrue(is_repo_url("https://gitlab.com/owner/repo"))

    def test_bitbucket_plain(self):
        self.assertTrue(is_repo_url("https://bitbucket.org/owner/repo"))

    def test_owner_with_hyphens_and_dots(self):
        self.assertTrue(is_repo_url("https://github.com/my-org/my.repo"))

    def test_leading_whitespace_stripped(self):
        self.assertTrue(is_repo_url("  https://github.com/owner/repo  "))

    # ── invalid URLs ─────────────────────────────────────────────────────────

    def test_local_absolute_path(self):
        self.assertFalse(is_repo_url("/home/user/myproject"))

    def test_local_relative_path(self):
        self.assertFalse(is_repo_url("./myproject"))

    def test_ssh_url(self):
        self.assertFalse(is_repo_url("git@github.com:owner/repo.git"))

    def test_http_not_https(self):
        self.assertFalse(is_repo_url("http://github.com/owner/repo"))

    def test_unknown_host(self):
        self.assertFalse(is_repo_url("https://example.com/owner/repo"))

    def test_missing_repo_segment(self):
        self.assertFalse(is_repo_url("https://github.com/owner"))

    def test_empty_string(self):
        self.assertFalse(is_repo_url(""))

    def test_plain_word(self):
        self.assertFalse(is_repo_url("notaurl"))

    def test_windows_path(self):
        self.assertFalse(is_repo_url(r"C:\Users\user\project"))


# ---------------------------------------------------------------------------
# analyze_remote_repository() — error-path tests (no real network needed)
# ---------------------------------------------------------------------------

class TestAnalyzeRemoteRepositoryErrors(unittest.TestCase):
    """Error paths that can be exercised without a real network or git clone."""

    def test_blank_url_returns_error(self):
        result = analyze_remote_repository("")
        self.assertEqual(result["status"], "error")
        self.assertIn("blank", result["error"].lower())

    def test_invalid_url_returns_error(self):
        result = analyze_remote_repository("not-a-url")
        self.assertEqual(result["status"], "error")
        self.assertIn("Unsupported", result["error"])

    def test_local_path_returns_error(self):
        result = analyze_remote_repository("/tmp/localrepo")
        self.assertEqual(result["status"], "error")

    @patch("analyzer.repository_cloner._git_available", return_value=False)
    def test_git_not_available_returns_error(self, _mock):
        result = analyze_remote_repository("https://github.com/owner/repo")
        self.assertEqual(result["status"], "error")
        self.assertIn("git", result["error"].lower())

    @patch("analyzer.repository_cloner._git_available", return_value=True)
    @patch("analyzer.repository_cloner.subprocess.run")
    def test_clone_nonzero_exit_returns_error(self, mock_run, _mock_git):
        mock_run.return_value = MagicMock(
            returncode=128,
            stderr="fatal: repository 'https://github.com/owner/repo/' not found",
        )
        result = analyze_remote_repository("https://github.com/owner/repo")
        self.assertEqual(result["status"], "error")
        self.assertIn("git clone failed", result["error"])
        self.assertIn("128", result["error"])

    @patch("analyzer.repository_cloner._git_available", return_value=True)
    @patch("analyzer.repository_cloner.subprocess.run",
           side_effect=__import__("subprocess").TimeoutExpired(cmd="git", timeout=1))
    def test_clone_timeout_returns_error(self, _mock_run, _mock_git):
        result = analyze_remote_repository("https://github.com/owner/repo")
        self.assertEqual(result["status"], "error")
        self.assertIn("timed out", result["error"].lower())

    @patch("analyzer.repository_cloner._git_available", return_value=True)
    @patch("analyzer.repository_cloner.subprocess.run", return_value=MagicMock(returncode=0, stderr=""))
    @patch("analyzer.repository_cloner.analyze_repository",
           return_value={"status": "error", "repo_path": "/tmp/x", "error": "inner error"})
    def test_analyzer_error_preserved(self, _mock_analyze, _mock_run, _mock_git):
        result = analyze_remote_repository("https://github.com/owner/repo")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "inner error")

    @patch("analyzer.repository_cloner._git_available", return_value=True)
    @patch("analyzer.repository_cloner.subprocess.run", return_value=MagicMock(returncode=0, stderr=""))
    @patch("analyzer.repository_cloner.analyze_repository", return_value={
        "status": "ok",
        "repo_path": "/tmp/repo_clone_xyz/repo",
        "total_files": 5,
        "languages": {"Python": 3},
        "important_files": {},
        "readme": {},
        "structure": {"type": "Python application", "has_tests": False,
                      "has_ci": False, "has_docker": False,
                      "top_level_dirs": [], "entry_points": []},
        "dependencies": [],
    })
    def test_success_replaces_temp_path_with_url(self, _mock_analyze, _mock_run, _mock_git):
        url = "https://github.com/owner/repo"
        result = analyze_remote_repository(url)
        self.assertEqual(result["status"], "ok")
        # The temp path must be replaced with the original URL
        self.assertEqual(result["repo_path"], url)
        # Existing fields are preserved
        self.assertEqual(result["total_files"], 5)


# ---------------------------------------------------------------------------
# Constants sanity check
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    def test_timeout_is_positive_int(self):
        self.assertIsInstance(CLONE_TIMEOUT_SECONDS, int)
        self.assertGreater(CLONE_TIMEOUT_SECONDS, 0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
