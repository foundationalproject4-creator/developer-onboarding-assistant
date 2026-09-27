"""
analyzer/repository_cloner.py — Git cloning layer for the Repository Analyzer.

Accepts a remote repository URL (GitHub, GitLab, Bitbucket), clones it into
a temporary directory using the system ``git`` executable, runs the existing
``analyze_repository()`` function on the clone, then deletes the clone
automatically.

Public interface
----------------
    from analyzer.repository_cloner import is_repo_url, analyze_remote_repository

    # Detect whether a string is a remote URL (vs. a local path)
    if is_repo_url(user_input):
        result = analyze_remote_repository(user_input)
    else:
        result = analyze_repository(user_input)

Design decisions
----------------
- Uses ``subprocess`` with an argument **list** (never ``shell=True``) to
  prevent shell-injection attacks.
- Uses ``tempfile.TemporaryDirectory`` so the clone is always removed, even
  if analysis raises an exception.
- Requires only the system ``git`` binary — no GitHub tokens or API keys for
  public repositories.
- Does NOT modify ``analyzer/repository_analyzer.py`` in any way.
- All errors are returned as a dict ``{"status": "error", "error": "..."}``
  matching the existing analyzer error contract, so the FastAPI endpoint
  needs no special-casing.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from analyzer.repository_analyzer import analyze_repository

# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

# Matches public repository URLs on GitHub, GitLab, and Bitbucket.
# Accepts:
#   https://github.com/owner/repo
#   https://github.com/owner/repo.git
#   https://gitlab.com/owner/repo
#   https://bitbucket.org/owner/repo
#
# Does NOT accept:
#   - Non-HTTPS schemes (ssh://, git://) — those require credentials
#   - Sub-group GitLab paths (owner/group/repo) — kept simple intentionally
#   - Trailing path components beyond /owner/repo[.git][/]
_REPO_URL_RE = re.compile(
    r"^https://"
    r"(github\.com|gitlab\.com|bitbucket\.org)"
    r"/([A-Za-z0-9_.\-]+)"        # owner
    r"/([A-Za-z0-9_.\-]+)"        # repo name
    r"(\.git)?"                    # optional .git suffix
    r"/?$",                        # optional trailing slash
    re.IGNORECASE,
)

# Clone timeout in seconds.  Public repos on reasonable connections clone in
# well under 60 s for most projects.  Set higher for very large repos.
CLONE_TIMEOUT_SECONDS: int = 120


def is_repo_url(value: str) -> bool:
    """
    Return ``True`` if *value* looks like a supported remote repository URL.

    Only HTTPS URLs on GitHub, GitLab, or Bitbucket are accepted.
    Local paths, SSH URLs, and arbitrary HTTP URLs all return ``False``.

    Examples::

        is_repo_url("https://github.com/owner/repo")   # True
        is_repo_url("https://github.com/owner/repo.git")  # True
        is_repo_url("/home/user/myproject")            # False
        is_repo_url("git@github.com:owner/repo.git")  # False
    """
    return bool(_REPO_URL_RE.match(value.strip()))


def _normalise_url(url: str) -> str:
    """
    Return a clean clone URL:
    - Strips surrounding whitespace.
    - Removes a trailing slash so git clone gets a clean URL.
    - Does NOT add ``.git``; git handles both forms fine.
    """
    return url.strip().rstrip("/")


def _git_available() -> bool:
    """Return True if the ``git`` executable is on PATH."""
    return shutil.which("git") is not None


# ---------------------------------------------------------------------------
# Cloning + analysis
# ---------------------------------------------------------------------------

def analyze_remote_repository(repo_url: str) -> dict:
    """
    Clone *repo_url* into a temporary directory, run the Repository Analyzer
    on the clone, delete the clone, and return the analysis result.

    Parameters
    ----------
    repo_url:
        A public HTTPS repository URL, e.g.
        ``"https://github.com/owner/repository"``.

    Returns
    -------
    dict
        Exactly the same shape as ``analyze_repository()`` returns:

        On success::

            {
                "status": "ok",
                "repo_path": "<temp_clone_path>",
                "total_files": ...,
                ...
            }

        On failure::

            {
                "status": "error",
                "repo_path": "<url_or_temp_path>",
                "error": "<human-readable message>"
            }

    This function never raises — all errors are captured and returned as a
    dict so the FastAPI endpoint needs no special exception handling.
    """
    # ── Step 1: validate URL ─────────────────────────────────────────────────
    if not repo_url or not repo_url.strip():
        return {
            "status": "error",
            "repo_path": repo_url,
            "error": "Repository URL must not be blank.",
        }

    if not is_repo_url(repo_url):
        return {
            "status": "error",
            "repo_path": repo_url,
            "error": (
                "Unsupported repository URL. "
                "Please provide a public HTTPS URL from GitHub, GitLab, or Bitbucket. "
                f"Got: {repo_url!r}"
            ),
        }

    # ── Step 2: check git is available ───────────────────────────────────────
    if not _git_available():
        return {
            "status": "error",
            "repo_path": repo_url,
            "error": (
                "The 'git' executable was not found on this server. "
                "Please ensure git is installed in the deployment environment."
            ),
        }

    clean_url = _normalise_url(repo_url)

    # ── Step 3: clone into a temp dir, analyze, clean up ────────────────────
    # ``tempfile.TemporaryDirectory`` is used as a context manager so the
    # directory is always removed — even if analysis raises an exception.
    try:
        with tempfile.TemporaryDirectory(prefix="repo_clone_") as tmp_dir:
            clone_path = str(Path(tmp_dir) / "repo")

            # ── Clone ────────────────────────────────────────────────────────
            # Arguments are passed as a list — never shell=True — to prevent
            # injection attacks if the URL somehow bypassed validation.
            # --depth 1: shallow clone for speed (we only need the file tree).
            # --single-branch: fetch only the default branch.
            # --no-tags: skip tag refs (not needed for analysis).
            clone_cmd = [
                "git", "clone",
                "--depth", "1",
                "--single-branch",
                "--no-tags",
                clean_url,
                clone_path,
            ]

            try:
                proc = subprocess.run(
                    clone_cmd,
                    capture_output=True,
                    text=True,
                    timeout=CLONE_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                return {
                    "status": "error",
                    "repo_path": repo_url,
                    "error": (
                        f"Repository clone timed out after {CLONE_TIMEOUT_SECONDS} seconds. "
                        "The repository may be too large or the network too slow."
                    ),
                }
            except FileNotFoundError:
                # Should not reach here given _git_available() check above,
                # but guard defensively in case of a race condition.
                return {
                    "status": "error",
                    "repo_path": repo_url,
                    "error": "git executable disappeared unexpectedly.",
                }

            if proc.returncode != 0:
                # Surface git's own error message for clarity.
                stderr_snippet = (proc.stderr or "").strip()
                # Truncate very long git output to keep the error readable.
                if len(stderr_snippet) > 400:
                    stderr_snippet = stderr_snippet[:400] + "…"
                return {
                    "status": "error",
                    "repo_path": repo_url,
                    "error": (
                        f"git clone failed (exit code {proc.returncode}). "
                        f"The repository may be private, misspelled, or unreachable. "
                        f"git output: {stderr_snippet}"
                    ),
                }

            # ── Analyze the clone ─────────────────────────────────────────────
            # analyze_repository() is the existing function — unchanged.
            result = analyze_repository(clone_path)

            # Replace the temp filesystem path with the original URL so the
            # caller/frontend sees the URL they submitted, not a temp path.
            if result.get("status") == "ok":
                result["repo_path"] = repo_url

            return result

    except Exception as exc:  # noqa: BLE001 — broad catch for API safety
        return {
            "status": "error",
            "repo_path": repo_url,
            "error": f"Unexpected error during remote analysis: {exc}",
        }
