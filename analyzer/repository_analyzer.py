"""
Developer Onboarding Assistant — Repository Analyzer
=====================================================
Meith's module: deterministic, AI-free analysis of a local repository.

Public interface
----------------
    from analyzer.repository_analyzer import analyze_repository

    result = analyze_repository("/path/to/some/repo")
    # result is a plain dict — safe to return directly from a FastAPI endpoint.

All heavy lifting is done with the Python standard library only (os, pathlib,
re, collections).  No third-party packages are required.
"""

import os
import re
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants — centralised so they are easy to extend
# ---------------------------------------------------------------------------

# Directories that should never be walked into.
IGNORED_DIRS: set[str] = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
    "htmlcov",
    "target",          # Rust / Maven
    ".gradle",
    ".idea",
    ".vscode",
    "__MACOSX",
    ".DS_Store",
}

# Map file extension → human-readable language name.
# Extensions are stored without the leading dot (matched after lower-casing).
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    # Python
    "py": "Python",
    "pyi": "Python",
    "ipynb": "Jupyter Notebook",
    # JavaScript / TypeScript
    "js": "JavaScript",
    "mjs": "JavaScript",
    "cjs": "JavaScript",
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "jsx": "JavaScript",
    # Web
    "html": "HTML",
    "htm": "HTML",
    "css": "CSS",
    "scss": "SCSS",
    "sass": "SASS",
    "less": "LESS",
    # JVM
    "java": "Java",
    "kt": "Kotlin",
    "kts": "Kotlin",
    "scala": "Scala",
    "groovy": "Groovy",
    # Systems
    "c": "C",
    "h": "C",
    "cpp": "C++",
    "cc": "C++",
    "cxx": "C++",
    "hpp": "C++",
    "rs": "Rust",
    "go": "Go",
    # Scripting
    "sh": "Shell",
    "bash": "Shell",
    "zsh": "Shell",
    "fish": "Shell",
    "ps1": "PowerShell",
    "rb": "Ruby",
    "php": "PHP",
    "pl": "Perl",
    "lua": "Lua",
    "r": "R",
    # Data / Config
    "sql": "SQL",
    "json": "JSON",
    "yaml": "YAML",
    "yml": "YAML",
    "toml": "TOML",
    "xml": "XML",
    "csv": "CSV",
    # Markup / Docs
    "md": "Markdown",
    "rst": "reStructuredText",
    "tex": "LaTeX",
    # Mobile
    "swift": "Swift",
    "dart": "Dart",
    # Other
    "tf": "Terraform",
    "hcl": "HCL",
    "ex": "Elixir",
    "exs": "Elixir",
    "hs": "Haskell",
    "clj": "Clojure",
    "erl": "Erlang",
    "vim": "VimScript",
}

# Files whose presence signals something important about the project.
# Key  = exact filename (case-insensitive match applied at scan time)
# Value = human-readable label shown in the analysis output.
IMPORTANT_FILES: dict[str, str] = {
    "readme.md": "README (Markdown)",
    "readme.rst": "README (reStructuredText)",
    "readme.txt": "README (plain text)",
    "readme": "README (plain text)",
    "requirements.txt": "Python dependencies (pip)",
    "pyproject.toml": "Python project config (PEP 517/518)",
    "setup.py": "Python setup script",
    "setup.cfg": "Python setup config",
    "pipfile": "Python dependencies (Pipenv)",
    "package.json": "Node.js project manifest",
    "package-lock.json": "Node.js lock file (npm)",
    "yarn.lock": "Node.js lock file (Yarn)",
    "pnpm-lock.yaml": "Node.js lock file (pnpm)",
    "cargo.toml": "Rust project manifest",
    "cargo.lock": "Rust lock file",
    "go.mod": "Go module definition",
    "go.sum": "Go module checksums",
    "pom.xml": "Java/Maven project descriptor",
    "build.gradle": "Java/Kotlin Gradle build script",
    "build.gradle.kts": "Kotlin Gradle build script",
    "dockerfile": "Docker container definition",
    "docker-compose.yml": "Docker Compose config",
    "docker-compose.yaml": "Docker Compose config",
    ".env.example": "Environment variable template",
    ".env.sample": "Environment variable template",
    "makefile": "Makefile (build automation)",
    "justfile": "Justfile (task runner)",
    "tox.ini": "Python tox config",
    ".flake8": "Python Flake8 config",
    ".eslintrc": "ESLint config",
    ".eslintrc.js": "ESLint config",
    ".eslintrc.json": "ESLint config",
    ".prettierrc": "Prettier config",
    "tsconfig.json": "TypeScript compiler config",
    ".travis.yml": "Travis CI config",
    ".github": "GitHub Actions / config directory",
    "jenkinsfile": "Jenkins pipeline",
    "sonar-project.properties": "SonarQube config",
    "license": "License file",
    "license.md": "License file",
    "license.txt": "License file",
    "changelog.md": "Changelog",
    "contributing.md": "Contribution guidelines",
    "code_of_conduct.md": "Code of conduct",
}

# README size guard — we read at most this many bytes to avoid loading huge files.
_README_MAX_BYTES: int = 8_192


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_repo_path(repo_path: str) -> Path:
    """
    Validate that *repo_path* exists and is a directory.

    Returns a resolved :class:`pathlib.Path` on success.
    Raises :class:`ValueError` with a descriptive message on failure.
    """
    if not repo_path or not repo_path.strip():
        raise ValueError("repo_path must not be blank.")

    path = Path(repo_path.strip()).resolve()

    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")

    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    return path


# ---------------------------------------------------------------------------
# Scanning helpers
# ---------------------------------------------------------------------------

def _walk_repository(root: Path) -> tuple[list[Path], list[Path]]:
    """
    Recursively walk *root*, skipping ignored directories.

    Returns a tuple of ``(all_files, all_dirs)`` where each element is a
    list of :class:`pathlib.Path` objects relative to *root*.
    """
    all_files: list[Path] = []
    all_dirs: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)

        # Prune ignored directories in-place so os.walk does not descend into them.
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORED_DIRS and not d.startswith(".")
            # Keep explicitly important dot-directories if needed in future;
            # for now a simple leading-dot guard is sufficient.
        ]

        for dirname in dirnames:
            all_dirs.append((current / dirname).relative_to(root))

        for filename in filenames:
            all_files.append((current / filename).relative_to(root))

    return all_files, all_dirs


def _detect_languages(files: list[Path]) -> dict[str, int]:
    """
    Count source-code file occurrences grouped by programming language.

    Returns a dict mapping language name → file count, sorted by count
    descending.
    """
    counter: Counter[str] = Counter()
    for file_path in files:
        ext = file_path.suffix.lstrip(".").lower()
        language = EXTENSION_TO_LANGUAGE.get(ext)
        if language:
            counter[language] += 1

    # Return as a plain dict, highest count first.
    return dict(counter.most_common())


def _detect_important_files(files: list[Path]) -> dict[str, str]:
    """
    Scan *files* for known important filenames.

    Returns a dict mapping the relative path string → human-readable label.
    """
    found: dict[str, str] = {}
    for file_path in files:
        name_lower = file_path.name.lower()
        label = IMPORTANT_FILES.get(name_lower)
        if label:
            found[str(file_path)] = label
    return found


# ---------------------------------------------------------------------------
# README extraction
# ---------------------------------------------------------------------------

def _extract_readme_info(root: Path, files: list[Path]) -> dict[str, str]:
    """
    Locate the top-level README and extract basic information from it.

    Extracts:
    - ``title``      — first H1 heading found (``# Title``), if any.
    - ``description`` — first non-empty paragraph of text after the title.
    - ``raw_excerpt`` — first ``_README_MAX_BYTES`` characters (for downstream use).

    Returns an empty dict if no README is found or the file cannot be read.
    """
    # Prefer a README at the repository root; fall back to any other README.
    readme_candidates = [
        f for f in files
        if f.name.lower().startswith("readme")
        and len(f.parts) == 1  # top-level only
    ]
    if not readme_candidates:
        # Accept a README one level deeper if no root README exists.
        readme_candidates = [f for f in files if f.name.lower().startswith("readme")]

    if not readme_candidates:
        return {}

    readme_path = root / readme_candidates[0]

    try:
        raw = readme_path.read_bytes()[:_README_MAX_BYTES].decode("utf-8", errors="replace")
    except OSError:
        return {}

    info: dict[str, str] = {"path": str(readme_candidates[0])}

    # Extract the first H1 heading.
    title_match = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
    if title_match:
        info["title"] = title_match.group(1).strip()

    # Extract the first meaningful paragraph (non-heading, non-blank, non-badge).
    # We skip lines that look like badges (![...]) or HTML tags.
    lines = raw.splitlines()
    paragraph_lines: list[str] = []
    in_paragraph = False
    for line in lines:
        stripped = line.strip()
        # Skip headings, blank lines (before we start), badges, HTML, code fences.
        if stripped.startswith("#"):
            if in_paragraph:
                break  # reached the next heading — stop
            continue
        if not stripped:
            if in_paragraph:
                break  # blank line ends the paragraph
            continue
        if stripped.startswith("![") or stripped.startswith("<") or stripped.startswith("```"):
            continue
        in_paragraph = True
        paragraph_lines.append(stripped)

    if paragraph_lines:
        info["description"] = " ".join(paragraph_lines)

    info["raw_excerpt"] = raw[:500]  # first 500 chars for a quick preview

    return info


# ---------------------------------------------------------------------------
# Project-structure detection
# ---------------------------------------------------------------------------

def _detect_project_structure(root: Path, dirs: list[Path], files: list[Path]) -> dict:
    """
    Infer high-level structural characteristics of the repository.

    Detects:
    - ``type``          — broad project type (e.g. "Python package", "Node.js app").
    - ``has_tests``     — whether a tests/test directory or test files were found.
    - ``has_ci``        — whether CI configuration was found.
    - ``has_docker``    — whether Docker-related files were found.
    - ``top_level_dirs`` — names of the first-level directories (excluding ignored ones).
    """
    top_level_dirs = [str(d) for d in dirs if len(d.parts) == 1]
    file_names_lower = {f.name.lower() for f in files}

    # --- project type heuristics ---
    project_type = "Unknown"
    if "pyproject.toml" in file_names_lower or "setup.py" in file_names_lower:
        project_type = "Python package"
    elif "requirements.txt" in file_names_lower and "manage.py" in file_names_lower:
        project_type = "Django application"
    elif "requirements.txt" in file_names_lower:
        project_type = "Python application"
    elif "package.json" in file_names_lower:
        if "angular.json" in file_names_lower:
            project_type = "Angular application"
        elif "next.config.js" in file_names_lower or "next.config.ts" in file_names_lower:
            project_type = "Next.js application"
        elif "vite.config.ts" in file_names_lower or "vite.config.js" in file_names_lower:
            project_type = "Vite application"
        else:
            project_type = "Node.js application"
    elif "cargo.toml" in file_names_lower:
        project_type = "Rust project"
    elif "go.mod" in file_names_lower:
        project_type = "Go module"
    elif "pom.xml" in file_names_lower or "build.gradle" in file_names_lower:
        project_type = "Java/JVM project"
    elif "dockerfile" in file_names_lower:
        project_type = "Containerised application"

    # --- tests ---
    test_dir_names = {"test", "tests", "spec", "specs", "__tests__"}
    has_tests = any(d.parts[-1].lower() in test_dir_names for d in dirs)
    if not has_tests:
        # Also check for test files anywhere in the tree.
        has_tests = any(
            f.name.lower().startswith("test_") or f.name.lower().endswith("_test.py")
            for f in files
        )

    # --- CI ---
    ci_markers = {
        ".travis.yml", ".travis.yaml",
        "jenkinsfile",
        ".circleci",   # directory
        "azure-pipelines.yml",
        "bitbucket-pipelines.yml",
    }
    has_ci = bool(ci_markers & file_names_lower)
    # Also check for a .github/workflows directory.
    if not has_ci:
        has_ci = any(
            len(d.parts) >= 2 and d.parts[0] == ".github" and d.parts[1] == "workflows"
            for d in dirs
        )

    # --- Docker ---
    docker_markers = {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}
    has_docker = bool(docker_markers & file_names_lower)

    return {
        "type": project_type,
        "has_tests": has_tests,
        "has_ci": has_ci,
        "has_docker": has_docker,
        "top_level_dirs": sorted(top_level_dirs),
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def analyze_repository(repo_path: str) -> dict:
    """
    Analyse a local repository and return a structured summary as a dict.

    Parameters
    ----------
    repo_path:
        Absolute or relative path to the repository root directory.

    Returns
    -------
    dict
        A plain Python dictionary containing:

        ``status``          — ``"ok"`` on success, ``"error"`` on failure.
        ``repo_path``       — The resolved absolute path that was analysed.
        ``total_files``     — Total number of files found (after ignoring dirs).
        ``total_dirs``      — Total number of directories found (after ignoring dirs).
        ``languages``       — Dict of language → file count, sorted by count.
        ``important_files`` — Dict of relative path → label for notable files.
        ``readme``          — Extracted README info (title, description, excerpt).
        ``structure``       — High-level structural characteristics.
        ``error``           — (only present on failure) Human-readable error message.

    Raises
    ------
    This function never raises — errors are captured and returned in the dict
    so that a FastAPI endpoint can relay them cleanly to the caller.
    """
    try:
        root = _validate_repo_path(repo_path)
    except ValueError as exc:
        return {
            "status": "error",
            "repo_path": repo_path,
            "error": str(exc),
        }

    try:
        files, dirs = _walk_repository(root)
        languages = _detect_languages(files)
        important_files = _detect_important_files(files)
        readme_info = _extract_readme_info(root, files)
        structure = _detect_project_structure(root, dirs, files)

        return {
            "status": "ok",
            "repo_path": str(root),
            "total_files": len(files),
            "total_dirs": len(dirs),
            "languages": languages,
            "important_files": important_files,
            "readme": readme_info,
            "structure": structure,
        }

    except Exception as exc:  # noqa: BLE001 — broad catch intentional for API safety
        return {
            "status": "error",
            "repo_path": str(root),
            "error": f"Unexpected error during analysis: {exc}",
        }
