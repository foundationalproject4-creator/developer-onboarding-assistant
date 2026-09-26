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

import json
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

# Dependency files we know how to parse, in the order we prefer to display them.
# Each entry is the lower-cased filename; matching is case-insensitive at scan time.
_DEPENDENCY_FILES: tuple[str, ...] = (
    "requirements.txt",
    "package.json",
    "pyproject.toml",
    "go.mod",
    "cargo.toml",
)


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
# Dependency extraction
# ---------------------------------------------------------------------------

def _parse_requirements_txt(path: Path) -> list[str]:
    """
    Parse a pip-style requirements.txt file and return clean package names.

    Rules applied to each line:
    - Blank lines and comment lines (starting with #) are skipped.
    - Lines starting with -r, -c, -e, or other pip options are skipped.
    - Version specifiers (==, >=, <=, ~=, !=, >, <) and everything after
      them are stripped — we want only the bare package name.
    - Extras (e.g. "requests[security]") are kept as-is so the name
      remains readable, but the brackets could be stripped in future.
    """
    packages: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return packages

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Skip blank lines and comments.
        if not line or line.startswith("#"):
            continue

        # Skip pip option flags like -r other.txt, -c constraints.txt, -e .
        if line.startswith("-"):
            continue

        # Strip inline comments (e.g. "requests>=2.0  # HTTP library").
        line = line.split("#")[0].strip()

        # Remove version specifier — split on the first occurrence of any
        # version operator.  The regex matches ==, >=, <=, ~=, !=, >, <.
        name = re.split(r"[><=!~;@]", line)[0].strip()

        if name:
            packages.append(name)

    return packages


def _parse_package_json(path: Path) -> list[str]:
    """
    Parse a Node.js package.json and return all dependency package names
    from both "dependencies" and "devDependencies".
    """
    packages: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return packages

    # Both sections are optional — .get() returns an empty dict if missing.
    deps = data.get("dependencies", {})
    dev_deps = data.get("devDependencies", {})

    # Keys are package names; values are version strings — we only want names.
    packages.extend(deps.keys())
    packages.extend(dev_deps.keys())

    return packages


def _parse_pyproject_toml(path: Path) -> list[str]:
    """
    Parse a pyproject.toml file using only the standard library and return
    declared dependency names.

    Python's standard library does not include a TOML parser before 3.11.
    Strategy:
    - On Python 3.11+ use the built-in ``tomllib``.
    - On older versions fall back to a simple line-by-line regex scan that
      catches the most common formats without needing third-party libraries.

    Looks for dependencies in:
    - [project] dependencies = [...]          (PEP 621 / Hatch / Flit)
    - [tool.poetry.dependencies]              (Poetry)
    """
    packages: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return packages

    # --- Try the built-in tomllib first (Python 3.11+) ---
    try:
        import tomllib  # available in Python 3.11+
        data = tomllib.loads(text)

        # PEP 621 style: [project] → dependencies = ["requests>=2", ...]
        project_deps = data.get("project", {}).get("dependencies", [])
        for dep in project_deps:
            # Each entry is a PEP 508 string like "requests>=2.0"
            name = re.split(r"[><=!~;\[@\s]", dep)[0].strip()
            if name:
                packages.append(name)

        # Poetry style: [tool.poetry.dependencies] → { "requests": "^2.0", ... }
        poetry_deps = (
            data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        )
        for name in poetry_deps:
            # "python" is a special key that specifies the Python version, not a package.
            if name.lower() != "python":
                packages.append(name)

        return packages

    except ImportError:
        pass  # Python < 3.11 — fall through to the regex approach

    # --- Regex fallback for Python < 3.11 ---
    # We look for lines that look like quoted dependency strings.
    # Handles both:
    #   "requests>=2.0",      (PEP 621 list items)
    #   requests = "^2.0"     (Poetry key = value)
    for line in text.splitlines():
        stripped = line.strip()

        # PEP 621 list item: starts with a quote inside a dependencies array.
        # e.g.   "fastapi>=0.100",
        pep621_match = re.match(r'^["\']([A-Za-z0-9_\-\.]+)', stripped)
        if pep621_match:
            packages.append(pep621_match.group(1))
            continue

        # Poetry key = value: e.g.  requests = "^2.28"
        poetry_match = re.match(r'^([A-Za-z0-9_\-\.]+)\s*=\s*["\'\{]', stripped)
        if poetry_match:
            name = poetry_match.group(1)
            # Skip TOML section-level keys that aren't packages.
            if name.lower() not in ("python", "name", "version", "description",
                                     "authors", "license", "readme", "requires"):
                packages.append(name)

    return packages


def _parse_go_mod(path: Path) -> list[str]:
    """
    Parse a Go go.mod file and return module dependency paths.

    Handles both single-line and block require forms:
        require github.com/some/module v1.2.3
        require (
            github.com/some/module v1.2.3
            github.com/other/dep   v0.1.0
        )

    Module paths with the "// indirect" comment are included — indirect
    dependencies are still real dependencies a new developer should know about.
    """
    packages: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return packages

    in_require_block = False

    for line in text.splitlines():
        stripped = line.strip()

        # Entering a require ( ... ) block.
        if re.match(r"^require\s*\(", stripped):
            in_require_block = True
            continue

        # Leaving the require block.
        if in_require_block and stripped == ")":
            in_require_block = False
            continue

        # Single-line: require github.com/foo/bar v1.0.0
        single = re.match(r"^require\s+(\S+)\s+", stripped)
        if single:
            packages.append(single.group(1))
            continue

        # Inside a block: each line is "module/path vX.Y.Z [// indirect]"
        if in_require_block and stripped and not stripped.startswith("//"):
            module_name = stripped.split()[0]
            if module_name:
                packages.append(module_name)

    return packages


def _parse_cargo_toml(path: Path) -> list[str]:
    """
    Parse a Rust Cargo.toml file and return dependency crate names from the
    [dependencies] section.

    Uses a simple line-by-line approach rather than a full TOML parser:
    - Watches for the [dependencies] section header.
    - Reads key = value lines until the next section header [ ... ].
    - Handles both:
        serde = "1.0"
        serde = { version = "1.0", features = ["derive"] }
    """
    packages: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return packages

    in_deps_section = False

    for line in text.splitlines():
        stripped = line.strip()

        # Detect section headers like [dependencies] or [dev-dependencies].
        if stripped.startswith("["):
            # We care about [dependencies] and [dev-dependencies].
            in_deps_section = stripped in ("[dependencies]", "[dev-dependencies]")
            continue

        if not in_deps_section:
            continue

        # Skip blank lines and comments.
        if not stripped or stripped.startswith("#"):
            continue

        # A dependency line looks like:  crate_name = "version"
        # or:  crate_name = { version = "...", ... }
        dep_match = re.match(r"^([A-Za-z0-9_\-]+)\s*=", stripped)
        if dep_match:
            packages.append(dep_match.group(1))

    return packages


def _extract_dependencies(root: Path, files: list[Path]) -> list[dict]:
    """
    Scan *files* for known dependency manifests, parse each one, and return
    a list of dicts — one per file found — in the form:

        [
            {
                "source":   "backend/requirements.txt",
                "packages": ["fastapi", "uvicorn", "pydantic"]
            },
            ...
        ]

    If no supported dependency file is present, an empty list is returned.
    Multiple files are all reported (requirement 11).
    """
    # Build a lookup: lower-cased filename → relative Path object.
    # This lets us do O(1) membership checks while preserving the real path.
    name_to_paths: dict[str, list[Path]] = {}
    for file_path in files:
        key = file_path.name.lower()
        if key in _DEPENDENCY_FILES:
            name_to_paths.setdefault(key, []).append(file_path)

    results: list[dict] = []

    # Iterate in the preferred display order defined by _DEPENDENCY_FILES.
    for dep_filename in _DEPENDENCY_FILES:
        for rel_path in name_to_paths.get(dep_filename, []):
            abs_path = root / rel_path

            if dep_filename == "requirements.txt":
                packages = _parse_requirements_txt(abs_path)
            elif dep_filename == "package.json":
                packages = _parse_package_json(abs_path)
            elif dep_filename == "pyproject.toml":
                packages = _parse_pyproject_toml(abs_path)
            elif dep_filename == "go.mod":
                packages = _parse_go_mod(abs_path)
            elif dep_filename == "cargo.toml":
                packages = _parse_cargo_toml(abs_path)
            else:
                packages = []  # should never happen given _DEPENDENCY_FILES

            results.append({
                "source": str(rel_path),   # relative path, e.g. "backend/requirements.txt"
                "packages": packages,
            })

    return results


# ---------------------------------------------------------------------------
# README extraction
# ---------------------------------------------------------------------------

def _extract_readme_sections(raw: str) -> dict[str, str]:
    """
    Parse a Markdown string and return a dict of heading → body text.

    Rules:
    - Only ``##`` and deeper headings become section keys (the ``#`` H1 title
      is already captured separately as ``info["title"]`` and is excluded).
    - A section's body is everything from the line after its heading up to
      (but not including) the next Markdown heading of equal or higher level.
    - ``---`` horizontal rules are treated as plain content and never act as
      section boundaries.
    - Lines inside fenced code blocks (``` ... ```) are never interpreted as
      headings, even if they start with ``#`` (e.g. shell comments).
    - Leading and trailing blank lines within each section body are stripped.
    - The heading text itself is used as the key, ``#`` prefix removed and
      surrounding whitespace trimmed.

    Example input fragment::

        ## Installation
        Run pip install -r requirements.txt

        ## Usage
        uvicorn main:app --reload

    Returns::

        {
            "Installation": "Run pip install -r requirements.txt",
            "Usage": "uvicorn main:app --reload",
        }
    """
    sections: dict[str, str] = {}

    # Matches a Markdown ATX heading: one to six # chars followed by a space
    # and at least one character of heading text.
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")

    # Matches the opening (or closing) fence of a fenced code block.
    # Accepts both ``` and ~~~ fences with optional language hints.
    fence_re = re.compile(r"^(`{3,}|~{3,})")

    lines = raw.splitlines()

    current_heading: str | None = None   # heading text of the open section
    current_level: int = 0               # # depth of that heading
    current_body: list[str] = []         # body lines accumulated so far
    in_fence: bool = False               # True while inside a fenced code block
    fence_marker: str = ""               # the exact opening fence (``` or ~~~)

    # Matches a standalone Markdown horizontal rule: a line consisting solely
    # of three or more dashes, asterisks, or underscores (with optional spaces).
    # e.g.  ---   ***   ___   - - -   * * *
    # Must be the entire line — "some text ---" is NOT a rule and is kept.
    hr_re = re.compile(r"^(\s*[-*_]){3,}\s*$")

    def _flush() -> None:
        """Save the currently open section into *sections*, then do nothing else."""
        if current_heading is not None:
            # Remove standalone horizontal-rule lines from the body before storing.
            cleaned = [ln for ln in current_body if not hr_re.match(ln)]
            body = "\n".join(cleaned).strip()
            if body:
                sections[current_heading] = body

    for line in lines:

        # ------------------------------------------------------------------ #
        # Track fenced code blocks.                                           #
        # A fence opens when we see ``` or ~~~ at the start of a line        #
        # (optionally followed by a language hint).                           #
        # It closes when we see the same or longer fence of the same type.   #
        # While inside a fence, ALL lines are body content — never headings. #
        # ------------------------------------------------------------------ #
        fence_match = fence_re.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                # Opening a new fence.
                in_fence = True
                fence_marker = marker[0]  # store just the character (' ` ' or '~')
            elif marker[0] == fence_marker:
                # Closing the current fence (same character type).
                in_fence = False
                fence_marker = ""
            # Either way, this line is body content — fall through to append below.

        # While inside a fence, skip heading detection entirely.
        if not in_fence and not fence_match:
            # Only attempt heading detection on lines that are outside a fence
            # AND are not themselves a fence marker.
            m = heading_re.match(line)
            if m:
                level = len(m.group(1))
                heading_text = m.group(2).strip()

                # H1 is stored as "title" elsewhere — skip it as a section key.
                if level == 1:
                    _flush()
                    current_heading = None
                    current_level = 0
                    current_body = []
                    continue

                # A heading at the same or shallower depth closes the open section.
                if current_heading is not None and level <= current_level:
                    _flush()
                    current_body = []

                # Open the new section.
                current_heading = heading_text
                current_level = level
                current_body = []
                continue   # the heading line itself is not part of the body

        # --------------------------------------------------------------- #
        # Everything that isn't a section-opening heading is body content. #
        # This includes: normal text, blank lines, --- rules, code lines,  #
        # and fence marker lines themselves.                                #
        # --------------------------------------------------------------- #
        if current_heading is not None:
            current_body.append(line)

    # Flush the final open section after the loop ends.
    _flush()

    return sections


def _extract_readme_info(root: Path, files: list[Path]) -> dict:
    """
    Locate the top-level README and extract basic information from it.

    Extracts:
    - ``title``       — first H1 heading found (``# Title``), if any.
    - ``description`` — first non-empty paragraph of text after the title.
    - ``raw_excerpt`` — first 500 characters (for downstream use).
    - ``sections``    — dict of ``## Heading`` name → body text for every
                        H2+ section found in the README.

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

    info: dict = {"path": str(readme_candidates[0])}

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

    # NEW: extract sections keyed by heading text (H2 and deeper only).
    info["sections"] = _extract_readme_sections(raw)

    return info


# ---------------------------------------------------------------------------
# Project-structure detection
# ---------------------------------------------------------------------------

# Common filenames that are likely application entry points, grouped by language.
# Order within each tuple matters — earlier entries are preferred when sorting.
_ENTRY_POINT_CANDIDATES: tuple[str, ...] = (
    # Python (highest priority first)
    "main.py",
    "app.py",
    "server.py",
    "manage.py",
    "__main__.py",
    # JavaScript / TypeScript
    "index.js",
    "index.ts",
    "server.js",
    "server.ts",
    "app.js",
    "app.ts",
    # Go / Rust
    "main.go",
    "main.rs",
)

# Build a quick lookup set for O(1) membership tests.
_ENTRY_POINT_NAMES: frozenset[str] = frozenset(_ENTRY_POINT_CANDIDATES)


def _detect_entry_points(root: Path, files: list[Path]) -> list[str]:
    """
    Scan *files* for likely application entry points and return their
    repository-relative paths as strings, deduplication guaranteed.

    Strategy
    --------
    1. Collect every scanned file whose lower-cased name is in
       ``_ENTRY_POINT_NAMES``.
    2. Additionally, read the ``"main"`` field from any ``package.json`` found
       in the file list — that field explicitly names the JS/TS entry point.
    3. Sort results by the priority order defined in
       ``_ENTRY_POINT_CANDIDATES`` (lower index = higher priority), then
       alphabetically within the same priority tier.
    4. Return relative path strings (forward-slash on all platforms for
       readability).

    These are *candidates*, not guarantees — the caller should treat them as
    "likely entry points".
    """
    seen: set[str] = set()       # deduplication
    results: list[str] = []

    # --- Step 1: filename matching ---
    # Build a priority lookup: filename → position in _ENTRY_POINT_CANDIDATES.
    priority: dict[str, int] = {
        name: idx for idx, name in enumerate(_ENTRY_POINT_CANDIDATES)
    }

    matches: list[tuple[int, str]] = []  # (priority_index, relative_path_str)

    for file_path in files:
        name_lower = file_path.name.lower()
        if name_lower in _ENTRY_POINT_NAMES:
            # Use forward slashes for cross-platform readability.
            rel = file_path.as_posix()
            if rel not in seen:
                seen.add(rel)
                matches.append((priority[name_lower], rel))

    # Sort: primary key = priority index (lower = more likely), secondary = path.
    matches.sort(key=lambda t: (t[0], t[1]))
    results.extend(rel for _, rel in matches)

    # --- Step 2: package.json "main" field ---
    for file_path in files:
        if file_path.name.lower() == "package.json":
            abs_path = root / file_path
            try:
                import json as _json
                data = _json.loads(abs_path.read_text(encoding="utf-8", errors="replace"))
                main_field = data.get("main", "")
                if isinstance(main_field, str) and main_field.strip():
                    # Resolve the "main" value relative to the package.json's
                    # own directory, then express it relative to the repo root.
                    pkg_dir = file_path.parent
                    candidate = (pkg_dir / main_field.strip()).as_posix()
                    # Normalise away any "./" prefix that package.json often uses.
                    candidate = candidate.lstrip("./") if candidate.startswith("./") else candidate
                    if candidate not in seen:
                        seen.add(candidate)
                        results.append(candidate)
            except (OSError, ValueError):
                pass  # unreadable or invalid JSON — skip silently

    return results


def _detect_project_structure(root: Path, dirs: list[Path], files: list[Path]) -> dict:
    """
    Infer high-level structural characteristics of the repository.

    Detects:
    - ``type``           — broad project type (e.g. "Python package", "Node.js app").
    - ``has_tests``      — whether a tests/test directory or test files were found.
    - ``has_ci``         — whether CI configuration was found.
    - ``has_docker``     — whether Docker-related files were found.
    - ``top_level_dirs`` — names of the first-level directories (excluding ignored ones).
    - ``entry_points``   — list of likely application entry-point paths (relative).
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

    # --- entry points ---
    entry_points = _detect_entry_points(root, files)

    return {
        "type": project_type,
        "has_tests": has_tests,
        "has_ci": has_ci,
        "has_docker": has_docker,
        "top_level_dirs": sorted(top_level_dirs),
        "entry_points": entry_points,
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

        dependencies = _extract_dependencies(root, files)

        return {
            "status": "ok",
            "repo_path": str(root),
            "total_files": len(files),
            "total_dirs": len(dirs),
            "languages": languages,
            "important_files": important_files,
            "readme": readme_info,
            "structure": structure,
            "dependencies": dependencies,
        }

    except Exception as exc:  # noqa: BLE001 — broad catch intentional for API safety
        return {
            "status": "error",
            "repo_path": str(root),
            "error": f"Unexpected error during analysis: {exc}",
        }
