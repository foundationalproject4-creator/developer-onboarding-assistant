"""
analyzer_adapter.py — Repository Analyzer → AI layer bridge.

Converts the native output of ``analyze_repository()`` (a plain dict produced
by ``analyzer.repository_analyzer``) into the dict shape expected by
``ai.schemas.RepoAnalysis``.

This file is intentionally self-contained:
  - No imports from the analyzer or the AI layer (avoids circular dependencies).
  - Pure Python standard library only.
  - No AI/LLM calls.

Usage::

    from analyzer.repository_analyzer import analyze_repository
    from backend.analyzer_adapter import to_repo_analysis

    raw = analyze_repository("/path/to/repo")
    payload = to_repo_analysis(raw)   # pass this to generate_onboarding()
"""


def to_repo_analysis(result: dict) -> dict:
    """
    Convert the dict returned by ``analyze_repository()`` into a dict that
    matches the ``ai.schemas.RepoAnalysis`` Pydantic model.

    Parameters
    ----------
    result:
        The dict returned by ``analyze_repository()``.  Must have
        ``"status": "ok"``; raises ``ValueError`` if the analyzer reported
        an error.

    Returns
    -------
    dict
        A plain dict with the keys ``project_name``, ``languages``,
        ``frameworks``, ``important_files``, ``dependencies``, and
        ``project_structure``.  Safe to pass directly to
        ``RepoAnalysis(**payload)`` or ``RepoAnalysis.model_validate(payload)``.
    """

    # ------------------------------------------------------------------
    # Guard: never silently convert a failed analysis result.
    # ------------------------------------------------------------------
    if result.get("status") == "error":
        raise ValueError(
            f"Repository Analyzer reported an error: "
            f"{result.get('error', 'unknown error')}"
        )

    # ------------------------------------------------------------------
    # 1. project_name — taken from the README title, if present.
    # ------------------------------------------------------------------
    readme = result.get("readme") or {}
    project_name = readme.get("title")  # str or None

    # ------------------------------------------------------------------
    # 2. languages — dict keys only (drop the file-count values).
    #    Analyzer:  {"Python": 12, "Markdown": 2}
    #    RepoAnalysis:  ["Python", "Markdown"]
    # ------------------------------------------------------------------
    languages = list(result.get("languages") or {})

    # ------------------------------------------------------------------
    # 3. frameworks — the analyzer does not detect frameworks yet.
    # ------------------------------------------------------------------
    frameworks: list = []

    # ------------------------------------------------------------------
    # 4. important_files — dict → list of {path, description} dicts.
    #    Analyzer:  {"backend/main.py": "FastAPI entry point"}
    #    RepoAnalysis:  [{"path": "backend/main.py",
    #                     "description": "FastAPI entry point"}]
    # ------------------------------------------------------------------
    important_files = [
        {"path": path, "description": label}
        for path, label in (result.get("important_files") or {}).items()
    ]

    # ------------------------------------------------------------------
    # 5. dependencies — flatten all package lists into one list of names.
    #    Analyzer:  [{"source": "requirements.txt",
    #                 "packages": ["fastapi", "uvicorn"]}]
    #    RepoAnalysis:  ["fastapi", "uvicorn"]
    # ------------------------------------------------------------------
    dependencies: list = []
    for entry in result.get("dependencies") or []:
        dependencies.extend(entry.get("packages") or [])

    # ------------------------------------------------------------------
    # 6. project_structure — key rename only; preserve the dict as-is.
    #    Analyzer key:  "structure"
    #    RepoAnalysis key:  "project_structure"
    # ------------------------------------------------------------------
    project_structure = result.get("structure")  # dict or None

    return {
        "project_name":      project_name,
        "languages":         languages,
        "frameworks":        frameworks,
        "important_files":   important_files,
        "dependencies":      dependencies,
        "project_structure": project_structure,
    }
