"""
Main entry point for the AI Analysis + Architecture layer.

    from ai.generator import generate_onboarding
    knowledge = generate_onboarding(repo_analysis)

Two paths:
1. LLM path — used when ANTHROPIC_API_KEY is set. The model turns the raw
   analyzer data into readable explanations, constrained by the prompt rules
   in prompts.py.  The LLM returns structured output via tool-use (function
   calling), so there is no JSON-text parsing or fence stripping here.
2. Fallback path — used when no API key is configured, or if the LLM call
   fails / returns an unexpected response. This is a purely rule-based
   assembly of the same output shape directly from the analyzer fields.
   It's less polished in prose but 100% grounded, so the rest of the team
   (and demo) is never blocked on API access.

Both paths always run the diagram generator separately and deterministically
(see diagram.py) rather than trusting the LLM to draw it.

``OnboardingKnowledge.used_llm`` is True only when the LLM path ran and
succeeded — useful for the frontend to show "AI-enhanced" vs "basic analysis".

Secret-leak policy
------------------
No API keys or credential values are ever written to logs or included in
exception messages that propagate to callers.  Specifically:
- ``LLMUnavailableError`` messages emitted here never contain the value of
  ANTHROPIC_API_KEY — only its name.
- Exception log lines use ``type(exc).__name__`` (not ``repr(exc)``) unless
  the exception is a controlled internal type (LLMUnavailableError), which
  is safe to log verbatim because it never embeds key material.
- The router catches all exceptions and returns a generic HTTP 500 message;
  no internal detail reaches the HTTP response body.

Pre-send sanitization
---------------------
``sanitize_analysis()`` (ai/sanitize.py) is called on every RepoAnalysis
before it is forwarded to the LLM.  It redacts strings matching common
API-key, token, and credential patterns so that secrets embedded in
repository metadata never reach the third-party API.

Cost budget cap
---------------
``AI_MAX_REQUESTS`` (env var, integer) sets a hard cap on the number of
LLM API calls this process will make before short-circuiting to fallback.
Defaults to unlimited (0 = no cap).  When the cap is reached, every
subsequent request silently uses the rule-based fallback path.
Set AI_MAX_REQUESTS=100 in production to guard against runaway cost from
a traffic spike.  Reset by restarting the process.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from .diagram import generate_architecture_diagram
from .llm_client import LLMUnavailableError, acall_llm, call_llm
from .metrics import ai_metrics
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from .sanitize import sanitize_analysis
from .schemas import (
    DependencyEntry,
    DependencyExplanation,
    ImportantFileEntry,
    ImportantFileExplanation,
    OnboardingKnowledge,
    RepoAnalysis,
    TechStackItem,
)

log = logging.getLogger(__name__)

# Sentinel text emitted by diagram.py when no architecture can be detected.
_DIAGRAM_UNKNOWN_SENTINEL = "Architecture not determinable from available data"

# Sentinel used whenever the analyzer gave us a name but no information about
# what it is for.  Never replace it with a guess.
_PURPOSE_UNKNOWN = "Purpose not specified by analyzer."

# Sentinel used when a whole list cannot be grounded in the analysis at all.
_NOT_DETECTED = "Not derivable from the provided analysis data."

# Shown when the analyzer found a project but no application entry point in it.
_NO_ENTRY_POINT_STEP = (
    "Start command: not detected — the analyzer did not report an "
    "application entry point."
)


# ---------------------------------------------------------------------------
# Dependency purpose catalog (rule-based path only)
# ---------------------------------------------------------------------------
# The rule-based fallback may state the role of a package whose *name* is
# unambiguous, and nothing else.  This mirrors SYSTEM_PROMPT rule 6 in
# prompts.py ("derive purpose only from the dependency name itself"): the
# lookup key is the exact package name, never the version, never the file it
# was declared in, and never anything repository-specific.
#
# The catalog is a static, project-independent name -> role map.  A package
# that is not listed keeps the "Purpose not specified by analyzer." sentinel so
# an unknown dependency is never given a fabricated description.
#
# Keep entries short and factual.  When adding one, describe the package's job,
# not how this particular repository uses it.
DEPENDENCY_PURPOSES: Dict[str, str] = {
    # ── Python: web frameworks and servers ────────────────────────────────
    "fastapi": "Python web framework used to define the HTTP API.",
    "starlette": "ASGI framework used to build the HTTP layer.",
    "flask": "Lightweight Python web framework used to define the routes.",
    "django": "Python web framework providing an ORM, admin site and templating.",
    "uvicorn": "ASGI server that runs the application in development.",
    "hypercorn": "ASGI/WSGI server used to serve the application.",
    "daphne": "ASGI server used to serve the application.",
    "gunicorn": "WSGI process manager used to serve the application in production.",
    "uvicorn-worker": "Process manager for running the ASGI application in production.",
    # ── Python: data, validation and config ───────────────────────────────
    "pydantic": "Data validation and settings modelling for app inputs and outputs.",
    "sqlalchemy": "SQL ORM and query toolkit used for database access.",
    "alembic": "Schema migration tool for the SQL database.",
    "databases": "Async database access layer used with an async web framework.",
    "redis": "In-memory key-value store used as a cache or a message broker.",
    "celery": "Distributed task queue used to run background jobs.",
    "pymongo": "MongoDB driver used for document database access.",
    "psycopg2": "PostgreSQL database driver.",
    "psycopg": "PostgreSQL database driver.",
    "asyncpg": "Async PostgreSQL database driver.",
    "mysqlclient": "MySQL database driver.",
    "pymysql": "Pure-Python MySQL database driver.",
    # ── Python: HTTP clients and integrations ─────────────────────────────
    "requests": "HTTP client used to call remote services.",
    "httpx": "Async-capable HTTP client used by the app and its tests.",
    "aiohttp": "Async HTTP client and server library.",
    "boto3": "AWS SDK for Python.",
    "anthropic": "Anthropic API client used to call the Claude models.",
    "openai": "OpenAI API client used to call the GPT models.",
    # ── Python: CLI, templating and utilities ──────────────────────────────
    "click": "Command-line argument parsing for the CLI entry point.",
    "typer": "Command-line interface builder built on click.",
    "rich": "Formatted terminal output used by the CLI.",
    "jinja2": "Templating engine used to render text templates.",
    "python-dotenv": "Loads values from a local .env file into the environment.",
    "python-dateutil": "Date parsing and arithmetic helpers.",
    "numpy": "N-dimensional array and numeric computation library.",
    "pandas": "Tabular data analysis library built on numpy.",
    "scipy": "Scientific computing and optimisation library.",
    "pillow": "Image loading and manipulation library.",
    # ── Python: tooling and tests ─────────────────────────────────────────
    "pytest": "Python test runner used by the test suite.",
    "pytest-asyncio": "Runs coroutine tests from pytest.",
    "httpx-ws": "WebSocket transport for the httpx client.",
    "black": "Opinionated Python code formatter.",
    "ruff": "Python linter and formatter run as a static check.",
    "flake8": "Python style and lint checks.",
    "pylint": "Python static analysis and lint checks.",
    "mypy": "Static type checker for the Python code.",
    "isort": "Import-order formatter for Python.",
    "coverage": "Measures which lines the test suite executes.",
    "hatchling": "Python build backend used by pyproject.toml.",
    "setuptools": "Python build and packaging backend.",
    "poetry": "Python dependency manager and build tool.",
    "pipenv": "Python virtualenv and dependency manager.",
    "anyio": "Async I/O library used by the async web stack.",
    # ── Frontend: UI libraries ────────────────────────────────────────────
    "react": "UI library used to build the component interface.",
    "react-dom": "Renders React components into the browser DOM.",
    "next": "Full-stack React framework providing routing, rendering and API routes.",
    "vue": "Progressive JavaScript UI framework.",
    "svelte": "Compiler-based UI framework.",
    "@sveltejs/kit": "Svelte application framework with routing and build tooling.",
    "angular": "TypeScript UI framework with dependency injection.",
    "@angular/core": "Core runtime of the Angular UI framework.",
    "preact": "Lightweight React-compatible UI library.",
    "solid-js": "Fine-grained reactive UI library.",
    "lit": "Web component UI library.",
    "ember-source": "Ember application framework.",
    # ── Frontend: build tooling ───────────────────────────────────────────
    "vite": "Development server and bundler for the frontend bundle.",
    "@vitejs/plugin-react": "Vite plugin providing React JSX handling and fast refresh.",
    "@vitejs/plugin-vue": "Vite plugin providing Vue single-file component support.",
    "@sveltejs/vite-plugin-svelte": "Vite plugin compiling Svelte components.",
    "webpack": "Module bundler used to build the frontend assets.",
    "rollup": "Module bundler used to produce the build output.",
    "esbuild": "Fast JavaScript/TypeScript transformer and bundler.",
    "parcel": "Zero-configuration application bundler.",
    "typescript": "Type-checked superset of JavaScript used by the build tool.",
    "tailwindcss": "Utility-first CSS framework used for styling.",
    "sass": "CSS preprocessor used by the stylesheet build.",
    "postcss": "CSS transformation plugin runner used by the build.",
    "autoprefixer": "Adds vendor prefixes to CSS during the build.",
    # ── Frontend: linting, formatting and tests ───────────────────────────
    "eslint": "Static analysis and lint rules for the JavaScript/TypeScript code.",
    "@eslint/js": "ESLint's shared recommended rule configurations.",
    "prettier": "Opinionated code formatter for the frontend sources.",
    "stylelint": "Linter for the stylesheets.",
    "jest": "JavaScript test runner.",
    "vitest": "Vite-native test runner.",
    "jsdom": "DOM implementation used to run tests outside a browser.",
    "@testing-library/react": "React component testing utilities.",
    "@testing-library/jest-dom": "Extra DOM matchers for Jest/Vitest assertions.",
    "cypress": "Browser-based end-to-end test runner.",
    "playwright": "Browser automation and end-to-end testing tool.",
    "globals": "Global variable definitions shared by the ESLint configs.",
    # ── Frontend: data and utilities ──────────────────────────────────────
    "mermaid": "Renders architecture diagrams from text-based diagram definitions.",
    "axios": "HTTP client used for browser or server requests.",
    "lodash": "General-purpose JavaScript utility helpers.",
    "d3": "Data visualisation library.",
    "chart.js": "Charting library for data visualisations.",
    "zustand": "Client-side state management store.",
    "redux": "Client-side state management store.",
    # ── Go ────────────────────────────────────────────────────────────────
    # go.mod yields fully-qualified module paths, so the keys must be too.
    "github.com/gin-gonic/gin": "Go HTTP web framework used to define the routes.",
    "github.com/labstack/echo": "Go HTTP web framework used to define the routes.",
    "github.com/gofiber/fiber": "Go web framework built on fasthttp.",
    "github.com/gorilla/mux": "Go HTTP router and middleware multiplexer.",
    "github.com/go-chi/chi": "Lightweight Go HTTP router.",
    "go.uber.org/zap": "Structured logging library for Go.",
    "github.com/stretchr/testify": "Assertion and mocking helpers for Go tests.",
    "github.com/sirupsen/logrus": "Structured logging library for Go.",
    "github.com/gorilla/websocket": "WebSocket implementation for Go.",
    "github.com/jackc/pgx": "PostgreSQL driver for Go.",
    "gorm.io/gorm": "ORM and database access layer for Go.",
    # ── Rust ──────────────────────────────────────────────────────────────
    "tokio": "Asynchronous runtime and task scheduler for Rust.",
    "serde": "Serialisation and deserialisation of Rust structs.",
    "actix-web": "Rust web framework used to define the routes.",
    "axum": "Rust web framework used to define the routes.",
    "anyhow": "Error handling helper for Rust applications.",
    # ── Java / JVM ────────────────────────────────────────────────────────
    "spring-boot-starter-web": "Spring Boot starter for web endpoints.",
    "spring-boot-starter": "Spring Boot application starter.",
    "lombok": "Compile-time boilerplate reduction for Java classes.",
    "junit-jupiter": "JUnit 5 test engine.",
}

# ---------------------------------------------------------------------------
# Cost budget cap
# ---------------------------------------------------------------------------
# AI_MAX_REQUESTS: maximum number of real LLM calls per process lifetime.
# 0 (default) means unlimited.  Set to a positive integer in production to
# guard against runaway cost from unexpected traffic spikes.
# The counter resets on process restart; for a persistent cap across restarts
# use an external counter (Redis INCR / a persistent store).

_budget_lock = threading.Lock()
_budget_llm_calls = 0  # count of LLM calls made this process lifetime


def _budget_check() -> bool:
    """
    Return True if the LLM call is allowed under the current budget.
    Return False (and log a warning) if the cap has been reached.
    Increments the counter if the call is allowed.
    """
    global _budget_llm_calls
    cap = int(os.environ.get("AI_MAX_REQUESTS", "0") or "0")
    if cap <= 0:
        return True  # no cap configured
    with _budget_lock:
        if _budget_llm_calls >= cap:
            log.warning(
                "ai.budget_cap: AI_MAX_REQUESTS=%d reached (%d calls made); "
                "short-circuiting to rule-based fallback for this request.",
                cap,
                _budget_llm_calls,
                extra={
                    "json_fields": {
                        "event": "ai.budget_cap",
                        "cap": cap,
                        "calls_made": _budget_llm_calls,
                    }
                },
            )
            return False
        _budget_llm_calls += 1
        return True


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
# Simple TTL cache keyed by a SHA-256 hash of the serialised RepoAnalysis.
# Identical repeated requests (same project, same deps, same structure) skip
# the LLM call entirely, saving both latency and API cost.
#
# For multi-process deployments (e.g. multiple Uvicorn workers or Kubernetes
# pods) swap this for a shared Redis store — the interface is the same: a
# dict keyed by hash, value is (result, expires_at).  The TTL is kept short
# (5 min) so stale data doesn't linger after the repo analysis changes.
#
# Redis would be warranted if you see a meaningful cache hit rate in
# production and need the cache to survive restarts.

_CACHE_TTL_SECONDS = 300  # 5 minutes
_cache: Dict[str, tuple[OnboardingKnowledge, float]] = {}


def _cache_key(analysis: RepoAnalysis) -> str:
    payload = analysis.model_dump_json(exclude_none=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_get(key: str) -> Optional[OnboardingKnowledge]:
    entry = _cache.get(key)
    if entry is None:
        return None
    result, expires_at = entry
    if time.monotonic() > expires_at:
        del _cache[key]
        return None
    return result


def _cache_set(key: str, result: OnboardingKnowledge) -> None:
    _cache[key] = (result, time.monotonic() + _CACHE_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Small normalisation helpers (handle Union[str, EntryModel] inputs)
# ---------------------------------------------------------------------------

def _file_to_explanation(f: Union[str, ImportantFileEntry]) -> ImportantFileExplanation:
    if isinstance(f, ImportantFileEntry):
        return ImportantFileExplanation(
            path=f.path,
            purpose=f.description or _PURPOSE_UNKNOWN,
        )
    return ImportantFileExplanation(path=f, purpose=_PURPOSE_UNKNOWN)


def _normalise_dep_name(name: str) -> str:
    """
    Reduce a dependency name to its bare, comparable form.

    Strips extras, version specifiers and an ``@version`` suffix and lower-cases
    the result, so ``uvicorn[standard]``, ``uvicorn`` and ``Uvicorn==0.34.2`` all
    normalise to ``uvicorn``.  A *leading* ``@`` is kept because scoped npm
    names such as ``@types/react`` are part of the name, not a version marker.
    """
    cleaned = re.split(r"[<>=!~;\[\s]", name.strip(), maxsplit=1)[0]
    at = cleaned.find("@", 1)
    if at > 0:
        cleaned = cleaned[:at]
    return cleaned.lower()


def _dependency_purpose(name: str) -> str:
    """
    Return a short purpose for *name*, or the sentinel when it is unknown.

    The lookup is by exact package name only.  Two npm naming conventions are
    additionally handled because they are fully determined by the name itself:

    * ``@types/<pkg>``          -> TypeScript type declarations for ``<pkg>``
    * ``eslint-plugin-<name>`` -> ESLint rule set for ``<name>``

    Anything else keeps ``_PURPOSE_UNKNOWN`` — we never guess.
    """
    key = _normalise_dep_name(name)
    purpose = DEPENDENCY_PURPOSES.get(key)
    if purpose:
        return purpose
    if key.startswith("@types/") and len(key) > len("@types/"):
        return f"TypeScript type declarations for {key[len('@types/'):]}."
    if key.startswith("eslint-plugin-") and len(key) > len("eslint-plugin-"):
        return f"ESLint rule set for {key[len('eslint-plugin-'):]}."
    return _PURPOSE_UNKNOWN


def _dep_to_explanation(d: Union[str, DependencyEntry]) -> DependencyExplanation:
    name = d.name if isinstance(d, DependencyEntry) else d
    return DependencyExplanation(name=name, purpose=_dependency_purpose(name))


def _dep_name(d: Union[str, DependencyEntry]) -> str:
    return d.name if isinstance(d, DependencyEntry) else d


# ---------------------------------------------------------------------------
# Deprecated: JSON fence stripping (kept for backward compat with tests only)
# ---------------------------------------------------------------------------

def _strip_json_fences(text: str) -> str:
    """
    .. deprecated::
        No longer used internally — the LLM now returns structured data via
        tool-use.  Kept only so existing test imports don't break.
    """
    import re
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
    return text


# ---------------------------------------------------------------------------
# Grounding audit
# ---------------------------------------------------------------------------

def _grounding_audit_failures(
    result: OnboardingKnowledge, analysis: RepoAnalysis
) -> List[str]:
    """
    Return a list of grounding-audit failure strings.

    A grounding failure is a field in the LLM output that references a name
    not present anywhere in the input.  We only check the most hallucination-
    prone fields (tech_stack names, important_files paths, dep names) against
    the union of all name-like strings in the input.

    This is a heuristic, not a proof — but it catches the most common cases
    and its failures are logged so we can track them over time.
    """
    # Build a set of all name-like strings from the input (lowercase).
    known: set = set()
    known.update(l.lower() for l in analysis.languages)
    known.update(f.lower() for f in analysis.frameworks)
    for dep in analysis.dependencies:
        known.add((dep.name if isinstance(dep, DependencyEntry) else dep).lower())
    for f in analysis.important_files:
        path = (f.path if isinstance(f, ImportantFileEntry) else f).lower()
        known.add(path)
        # Also add individual path components so "main.py" matches "backend/main.py"
        known.update(part.lower() for part in path.replace("\\", "/").split("/"))
    if analysis.project_name:
        known.add(analysis.project_name.lower())

    failures: List[str] = []

    for ts in result.tech_stack:
        if ts.name.lower() not in known:
            failures.append(f"tech_stack name not in input: {ts.name!r}")

    for imp in result.important_files:
        imp_lower = imp.path.lower()
        # Accept if any component of the path appears in known names
        parts = set(imp_lower.replace("\\", "/").split("/"))
        if imp_lower not in known and not parts.intersection(known):
            failures.append(f"important_files path not in input: {imp.path!r}")

    for dep in result.dependencies:
        if dep.name.lower() not in known:
            failures.append(f"dependency name not in input: {dep.name!r}")

    return failures


# ---------------------------------------------------------------------------
# Fallback (rule-based) path
# ---------------------------------------------------------------------------

def _fallback_overview(analysis: RepoAnalysis) -> str:
    """
    Build a grounded 2–4 sentence project overview from available analyzer
    fields.  Never invents information — every claim is derived directly from
    a non-empty field in *analysis*.
    """
    sentences: List[str] = []

    # ── Sentence 1: name + primary language(s) ──────────────────────────────
    lang_str = ", ".join(analysis.languages) if analysis.languages else None
    if analysis.project_name and lang_str:
        sentences.append(
            f"'{analysis.project_name}' is a software project primarily written in {lang_str}."
        )
    elif analysis.project_name:
        sentences.append(
            f"'{analysis.project_name}' is a software project."
        )
    elif lang_str:
        sentences.append(
            f"This project is primarily written in {lang_str}."
        )
    else:
        sentences.append("This project's name and primary language were not detected.")

    # ── Sentence 2: frameworks / main technologies ───────────────────────────
    if analysis.frameworks:
        fw_str = ", ".join(analysis.frameworks)
        sentences.append(f"It makes use of {fw_str}.")

    # ── Sentence 3: how the repo is organized ────────────────────────────────
    # Derive top-level directory names from project_structure or important_files.
    top_dirs: List[str] = []
    if isinstance(analysis.project_structure, dict):
        # Prefer an explicit 'top_level_dirs' list when the analyzer emits one;
        # fall back to the dict keys only if no such key exists (plain dir→files map).
        if "top_level_dirs" in analysis.project_structure:
            raw = analysis.project_structure["top_level_dirs"]
            if isinstance(raw, list):
                top_dirs = [str(d) for d in raw if d]
        else:
            top_dirs = [k for k in analysis.project_structure.keys() if k]
    elif isinstance(analysis.project_structure, list) and analysis.project_structure:
        # Flat path list — collect unique top-level segments.
        seen: set = set()
        for path in analysis.project_structure:
            segment = path.replace("\\", "/").split("/")[0]
            if segment and segment not in seen:
                seen.add(segment)
                top_dirs.append(segment)
    elif analysis.important_files:
        # Fall back to top-level prefixes from important_files paths.
        seen = set()
        for entry in analysis.important_files:
            raw = entry.path if isinstance(entry, ImportantFileEntry) else entry
            parts = raw.replace("\\", "/").split("/")
            if len(parts) > 1 and parts[0] not in seen:
                seen.add(parts[0])
                top_dirs.append(parts[0])

    if top_dirs:
        dirs_str = ", ".join(f"'{d}'" for d in top_dirs[:6])
        sentences.append(
            f"The repository is organized into the following top-level directories: {dirs_str}."
        )

    # ── Sentence 4: full dependency list ─────────────────────────────────────
    if analysis.dependencies:
        dep_names = [_dep_name(d) for d in analysis.dependencies]
        sentences.append(
            f"Key dependencies include {', '.join(dep_names)}."
        )

    return " ".join(sentences)


# ---------------------------------------------------------------------------
# Repository signal detection for the rule-based path
# ---------------------------------------------------------------------------
# Every rule below is driven by a *file the analyzer actually reported* or by a
# field of ``project_structure``.  Nothing assumes a project layout: when a
# signal is absent the corresponding step is simply not emitted, or the step
# says plainly that the detail was not detected.
#
# The manifest set is deliberately limited to the five files the analyzer can
# actually parse into dependencies (see analyzer._DEPENDENCY_FILES) plus the
# lock files and env templates it labels as important files.  A file outside
# that set is never turned into a command.

# File-path fragments whose presence implies a particular workflow signal.
# All comparisons are done on the lowercased normalised path.
_ENV_FILE_SIGNALS    = {".env", ".env.example", ".env.sample", ".env.local", "config.yaml", "config.yml", "config.json", ".envrc"}
_TEST_DIR_SIGNALS    = {"tests", "test", "__tests__", "spec", "specs", "e2e"}
_TEST_FILE_SIGNALS   = ("test_", "_test.", ".test.", ".spec.")
_FRONTEND_FILES      = {"package.json", "vite.config.js", "vite.config.ts", "next.config.js", "next.config.ts", "webpack.config.js"}
_FRONTEND_FRAMEWORKS = {"react", "vue", "angular", "svelte", "next", "nextjs", "nuxt", "vite"}
_BACKEND_ENTRY_EXTS  = {".py", ".go", ".java", ".rb", ".rs", ".ts", ".js", ".php"}
_BACKEND_ENTRY_NAMES = {"main.py", "app.py", "server.py", "manage.py", "main.go", "main.ts", "main.js",
                        "index.ts", "index.js", "app.ts", "app.js", "server.ts", "server.js",
                        "main.rb", "main.rs", "main.java"}

# Keys the analyzer adds to ``project_structure`` that are metadata rather than
# directory names (see analyzer._detect_project_structure).  They must never be
# treated as paths, otherwise a "directory" called "entry_points" would leak
# into the generated commands.
_STRUCTURE_METADATA_KEYS = frozenset({
    "type", "has_tests", "has_ci", "has_docker", "top_level_dirs", "entry_points",
})

# pip requirement files (any requirements*.txt) map to `pip install -r`.
_PY_REQUIREMENT_RE = re.compile(r"^requirements.*\.txt$")

# Env templates that exist precisely to be copied into a local env file.
_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template", ".env.dist"})

# npm lock files tell us which package manager the repository actually pins.
_LOCKFILE_TO_PM = {
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
}

# Container definition files detected by the analyzer.
_CONTAINER_FILES = frozenset({
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml",
})

# ASGI servers and frameworks, used only to pick a run command for a Python
# entry point.  Both must be present before an ``uvicorn module:app`` command is
# emitted, because that command encodes two assumptions (an ASGI app and the
# conventional ``app`` attribute name).
_ASGI_SERVERS = frozenset({"uvicorn", "hypercorn", "daphne"})
_ASGI_FRAMEWORKS = frozenset({"fastapi", "starlette", "falcon", "sanic", "litestar", "quart"})


def _posix(path: str) -> str:
    """Forward-slash-normalise a path so commands are identical on every OS."""
    return str(path).replace("\\", "/")


def _basename(path: str) -> str:
    return _posix(path).split("/")[-1]


def _dir_of(path: str) -> str:
    """Directory part of *path*, or "" when the file sits at the repo root."""
    posix = _posix(path)
    return posix.rsplit("/", 1)[0] if "/" in posix else ""


def _run_in(directory: str, command: str) -> str:
    """Prefix *command* with a ``cd`` when it must run inside *directory*."""
    return f"cd {directory} && {command}" if directory else command


def _structure(analysis: RepoAnalysis) -> Dict[str, Any]:
    """``project_structure`` as a dict, or an empty dict for the other shapes."""
    structure = analysis.project_structure
    return structure if isinstance(structure, dict) else {}


def _structure_flag(analysis: RepoAnalysis, name: str) -> bool:
    """Read a boolean flag the analyzer set on ``project_structure``."""
    return bool(_structure(analysis).get(name))


def _normalised_paths(analysis: RepoAnalysis) -> List[str]:
    """Return a flat list of lowercased, forward-slash-normalised paths
    drawn from both *important_files* and *project_structure*."""
    return [p.lower() for p in _detected_files(analysis)]


def _detected_files(analysis: RepoAnalysis) -> List[str]:
    """
    Every repository-relative file path the analyzer surfaced, de-duplicated and
    in a stable order (important files first, then structure entries).

    Handles all three ``project_structure`` shapes the analyzer/adapter can
    produce: the metadata dict, a plain ``dir -> [files]`` map, and a flat list
    of paths.  Metadata keys such as ``entry_points`` are skipped so they are
    never mistaken for directories.
    """
    paths: List[str] = []
    seen: set = set()

    def _add(candidate: str) -> None:
        posix = _posix(candidate).strip()
        # Normalise a leading "./" only — lstrip("./") would also eat the
        # leading dot of a file like ".env.example".
        if posix.startswith("./"):
            posix = posix[2:]
        if posix and posix not in seen:
            seen.add(posix)
            paths.append(posix)

    for entry in analysis.important_files:
        raw = entry.path if isinstance(entry, ImportantFileEntry) else entry
        _add(str(raw))

    structure = analysis.project_structure
    if isinstance(structure, dict):
        for key, value in structure.items():
            if key in _STRUCTURE_METADATA_KEYS:
                continue
            if isinstance(value, list):
                for item in value:
                    item_str = _posix(str(item))
                    _add(item_str if item_str.startswith("/") else f"{_posix(key)}/{item_str}")
    elif isinstance(structure, list):
        for item in structure:
            _add(str(item))

    return paths


def _detected_entry_points(analysis: RepoAnalysis) -> List[str]:
    """
    Application entry points, most likely first.

    Preference order:
      1. ``project_structure["entry_points"]`` — the analyzer's own ranked list.
      2. Well-known entry-point filenames among the detected files.
    """
    reported = _structure(analysis).get("entry_points")
    if isinstance(reported, list):
        candidates = [_posix(str(e)) for e in reported if str(e).strip()]
        if candidates:
            return candidates

    known = {
        "main.py", "app.py", "server.py", "manage.py", "main.go", "main.ts",
        "main.js", "index.ts", "index.js", "app.ts", "app.js", "server.ts",
        "server.js", "main.rb", "main.rs", "main.java", "__main__.py",
    }
    return [p for p in _detected_files(analysis) if _basename(p).lower() in known]


def _detected_dependency_names(analysis: RepoAnalysis) -> List[str]:
    return [_dep_name(d) for d in analysis.dependencies]


def _normalised_dependency_names(analysis: RepoAnalysis) -> set:
    return {_normalise_dep_name(name) for name in _detected_dependency_names(analysis)}


def _python_manifest_step(analysis: RepoAnalysis) -> Optional[str]:
    """
    Install command for the Python manifest the analyzer reported, or None.

    ``requirements*.txt`` -> ``pip install -r <file>`` is unambiguous.
    For ``pyproject.toml`` / ``setup.py`` we emit the conventional editable
    install of the directory that contains them, and flag the assumption.
    """
    files = _detected_files(analysis)
    requirements = next((p for p in files if _PY_REQUIREMENT_RE.match(_basename(p).lower())), None)
    if requirements:
        return f"python -m pip install -r {_posix(requirements)}"

    pyproject = next((p for p in files if _basename(p).lower() == "pyproject.toml"), None)
    if pyproject:
        return (
            f"{_run_in(_dir_of(pyproject), 'python -m pip install -e .')} "
            f"# editable install of the project in '{_posix(pyproject)}'"
        )

    setup_py = next((p for p in files if _basename(p).lower() == "setup.py"), None)
    if setup_py:
        return (
            f"{_run_in(_dir_of(setup_py), 'python -m pip install -e .')} "
            f"# editable install of the project in '{_posix(setup_py)}'"
        )

    return None


def _package_manager_for(directory: str, files: List[str]) -> Optional[str]:
    """
    Package manager pinned by a lock file in *directory*, or None if unpinned.

    Looking the lock file up in the *same* directory as ``package.json`` avoids
    attributing a monorepo's root lock file to a workspace package that does
    not declare one.
    """
    for path in files:
        if _dir_of(path) == directory and _basename(path).lower() in _LOCKFILE_TO_PM:
            return _LOCKFILE_TO_PM[_basename(path).lower()]
    return None


def _node_install_steps(analysis: RepoAnalysis) -> Tuple[List[str], List[str]]:
    """
    Install steps for every ``package.json`` the analyzer reported.

    Returns ``(steps, gaps)`` where *gaps* lists the details we could not
    determine (package manager, start script) so the caller can say so
    explicitly instead of guessing.
    """
    steps: List[str] = []
    gaps: List[str] = []
    files = _detected_files(analysis)

    for manifest in (p for p in files if _basename(p).lower() == "package.json"):
        directory = _dir_of(manifest)
        package_manager = _package_manager_for(directory, files)
        if package_manager is None:
            package_manager = "npm"
            gaps.append(
                f"no lock file next to '{_posix(manifest)}' was detected "
                f"({' / '.join(sorted(_LOCKFILE_TO_PM))}), so npm is assumed"
            )
        steps.append(_run_in(directory, f"{package_manager} install"))

    return steps, gaps


def _node_start_step(directory: str, manifest: str, package_manager: Optional[str]) -> Tuple[str, str]:
    """``<pm> run dev`` command for *directory* plus the caveat to show with it."""
    pm = package_manager or "npm"
    return (
        _run_in(directory, f"{pm} run dev"),
        f"the 'dev' script in '{_posix(manifest)}' was not detected "
        f"(the analyzer reads dependencies, not scripts) — list them with "
        f"'{_run_in(directory, f'{pm} run')}'",
    )


def _start_command(analysis: RepoAnalysis, entry: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Run command for the entry point *entry*, and a caveat string when the
    command depends on something the analyzer cannot see.

    Returns ``(command, caveat)``; *command* is None when the entry point needs
    a build step (or a container runtime) that we cannot verify.
    """
    name = _basename(entry).lower()
    path = _posix(entry)
    deps = _normalised_dependency_names(analysis)

    if name.endswith(".py"):
        module = path[:-3].replace("/", ".")
        if deps & _ASGI_SERVERS and deps & _ASGI_FRAMEWORKS:
            return (
                f"uvicorn {module}:app --reload",
                f"the ASGI application object name in '{path}' was not detected — "
                f"':app' assumes the conventional name",
            )
        if deps & _ASGI_SERVERS:
            return (
                f"uvicorn {module}:app --reload",
                f"no known ASGI framework was detected, so the object name in "
                f"'{path}' was not detected — confirm ':app'",
            )
        if "flask" in deps:
            return f"flask --app {module} run --debug", None
        return f"python {path}", None

    if name.endswith(".go"):
        return f"go run {path}", None

    if name.endswith((".js", ".mjs", ".cjs")):
        return f"node {path}", None

    if name.endswith((".ts", ".tsx", ".jsx")):
        return None, (
            f"'{path}' needs a build step before it can run, and the build command "
            f"was not detected by the analyzer"
        )

    return None, f"the run command for the entry point '{path}' was not detected"


def _docker_build_step(analysis: RepoAnalysis) -> Optional[str]:
    """``docker build`` command when a container definition file was detected."""
    files = _detected_files(analysis)
    if not any(_basename(p).lower() in _CONTAINER_FILES for p in files):
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", (analysis.project_name or "app").lower()).strip("-")
    return f"docker build -t {slug or 'app'} .  # Dockerfile detected at the repository root"


def _test_run_step(analysis: RepoAnalysis) -> Optional[str]:
    """
    Test command for a repository that has tests, or None when it has none.

    The command is chosen from the detected languages; when no runner matches
    the detected languages we say the runner was not detected.
    """
    paths = _normalised_paths(analysis)
    has_tests = _structure_flag(analysis, "has_tests")
    if not has_tests:
        has_tests = any(
            p.split("/")[0] in _TEST_DIR_SIGNALS
            or (len(p.split("/")) > 1 and p.split("/")[1] in _TEST_DIR_SIGNALS)
            or any(sig in _basename(p) for sig in _TEST_FILE_SIGNALS)
            for p in paths
        )
    if not has_tests:
        return None

    langs = {lang.lower() for lang in analysis.languages}
    deps = _normalised_dependency_names(analysis)
    files = _detected_files(analysis)
    has_package_json = any(_basename(p).lower() == "package.json" for p in files)

    if "python" in langs:
        return "python -m pytest  # run from the directory that contains the tests"
    if "go" in langs:
        return "go test ./..."
    if "rust" in langs:
        return "cargo test"
    if has_package_json or ("typescript" in langs and "javascript" in langs):
        return "npm test  # the test script in package.json was not detected by the analyzer"
    if deps & _TEST_DIR_SIGNALS or has_package_json:
        return "npm test"
    return "the test runner for this project was not detected by the analyzer"


def _env_config_steps(analysis: RepoAnalysis) -> Tuple[List[str], List[str]]:
    """
    Environment-configuration steps for env templates the analyzer reported.

    Returns ``(steps, gaps)``.  The variable *names* are never emitted because
    the analyzer reports the template file, not its contents — and a real
    ``.env`` is never read.
    """
    steps: List[str] = []
    gaps: List[str] = []

    for template in (p for p in _detected_files(analysis) if _basename(p).lower() in _ENV_TEMPLATES):
        directory = _dir_of(template)
        target = f"{directory}/.env" if directory else ".env"
        steps.append(
            f"cp {_posix(template)} {target} "
            f"# copy the template, then fill in the values it lists"
        )
        gaps.append(
            f"the variable names required by '{_posix(template)}' were not detected "
            f"(the analyzer reports the file, not its contents)"
        )

    # Configuration files that are not "copy me" templates: point at them, but
    # do not claim what belongs in them.
    for config in (p for p in _detected_files(analysis) if _basename(p).lower() in {"config.yaml", "config.yml", "config.json"}):
        if _basename(config).lower() in _ENV_TEMPLATES:
            continue
        steps.append(
            f"Review the configuration file '{_posix(config)}' before running the project."
        )

    return steps, gaps


def _node_start_steps(analysis: RepoAnalysis, backend_dir: str) -> Tuple[List[str], List[str]]:
    """
    Frontend dev-server steps for each ``package.json`` outside *backend_dir*.

    A ``package.json`` in the same directory as the detected server entry point
    is skipped: that is the server package, not a separate frontend.
    """
    steps: List[str] = []
    gaps: List[str] = []
    files = _detected_files(analysis)

    for manifest in (p for p in files if _basename(p).lower() == "package.json"):
        directory = _dir_of(manifest)
        if directory == backend_dir:
            continue
        package_manager = _package_manager_for(directory, files)
        command, caveat = _node_start_step(directory, manifest, package_manager)
        steps.append(command)
        gaps.append(caveat)

    return steps, gaps


def _unresolved_dependency_step(analysis: RepoAnalysis) -> Optional[str]:
    """
    Step used when dependencies were detected but no manifest file was.

    The names are known, the install command is not — say exactly that.
    """
    names = _detected_dependency_names(analysis)
    if not names:
        return None
    return (
        f"Dependencies detected: {', '.join(names)} — no dependency manifest "
        f"(requirements.txt, pyproject.toml, package.json, go.mod or Cargo.toml) "
        f"was detected, so the install command was not determined."
    )


def _fallback_starter_tasks(analysis: RepoAnalysis) -> List[str]:
    """
    Five grounded first tasks for a new developer on this repository.

    Each task names a concrete detected artefact (an important file, a
    dependency manifest, an entry point, a test suite, a top-level directory).
    When the corresponding signal is missing the task says so instead of
    implying the project has something it does not.
    """
    tasks: List[str] = []
    files = _detected_files(analysis)

    # 1. Start from the files the analyzer flagged as important.
    if analysis.important_files:
        first = analysis.important_files[0]
        first_path = _posix(
            first.path if isinstance(first, ImportantFileEntry) else str(first)
        )
        count = len(analysis.important_files)
        tasks.append(
            f"Read the {count} file(s) the analyzer flagged as important, starting "
            f"with '{first_path}', and note what each one is responsible for."
        )
    else:
        tasks.append(
            "No important files were detected by the analyzer — list the repository "
            "root and identify the main source directory yourself."
        )

    # 2. Follow the dependency manifests that actually exist.
    manifests = [
        p for p in files
        if _basename(p).lower() in {"package.json", "pyproject.toml", "go.mod", "cargo.toml"}
        or _PY_REQUIREMENT_RE.match(_basename(p).lower())
    ]
    if manifests:
        tasks.append(
            f"Open {' and '.join(repr(m) for m in manifests)} and find where the "
            f"declared dependencies are actually imported in the code."
        )
    else:
        tasks.append(
            "No dependency manifest was detected by the analyzer — ask a teammate "
            "which packages need to be installed before running the project."
        )

    # 3. Trace the code from the detected entry point.
    entries = _detected_entry_points(analysis)
    if entries:
        top_dirs = _structure(analysis).get("top_level_dirs")
        where = (
            f" through the top-level directories {', '.join(repr(d) for d in top_dirs)}"
            if isinstance(top_dirs, list) and top_dirs else ""
        )
        tasks.append(
            f"Trace the code path from the detected entry point '{_posix(entries[0])}'"
            f"{where}."
        )
    else:
        tasks.append(
            "No application entry point was detected by the analyzer — find the "
            "process that starts the project and work backwards from it."
        )

    # 4. Prove the local setup works.
    run_step = _test_run_step(analysis)
    if run_step:
        tasks.append(
            f"Get the project running locally and confirm the test suite passes "
            f"({run_step.split('#')[0].strip()})."
        )
    else:
        tasks.append(
            "No test suite was detected by the analyzer — start the project locally "
            "and confirm the main process comes up."
        )

    # 5. Make a small, low-risk change to learn the contribution flow.
    scope = _structure(analysis).get("top_level_dirs")
    where = (
        f" in '{_posix(str(scope[0]))}'" if isinstance(scope, list) and scope else ""
    )
    tasks.append(
        f"Make one small, low-risk change{where} — a documentation fix or a "
        f"clarifying comment — and open it as a review to learn the contribution flow."
    )

    return tasks


def _install_steps(analysis: RepoAnalysis) -> Tuple[List[str], List[str]]:
    """
    Install commands for the dependency manifests the analyzer reported.

    Returns ``(steps, gaps)``.  Covers exactly the ecosystems the analyzer can
    parse dependencies from; a manifest it cannot read is never turned into a
    command.
    """
    steps: List[str] = []
    gaps: List[str] = []
    files = _detected_files(analysis)

    python_step = _python_manifest_step(analysis)
    if python_step:
        steps.append(python_step)

    node_steps, node_gaps = _node_install_steps(analysis)
    steps.extend(node_steps)
    gaps.extend(node_gaps)

    go_mod = next((p for p in files if _basename(p).lower() == "go.mod"), None)
    if go_mod:
        steps.append(_run_in(_dir_of(go_mod), "go mod download"))

    cargo = next((p for p in files if _basename(p).lower() == "cargo.toml"), None)
    if cargo:
        steps.append(_run_in(_dir_of(cargo), "cargo fetch"))

    if not steps:
        # Dependencies were detected but no manifest was — name them and say
        # plainly that the install command is unknown.
        unresolved = _unresolved_dependency_step(analysis)
        if unresolved:
            steps.append(unresolved)

    return steps, gaps


def _application_start_steps(analysis: RepoAnalysis) -> Tuple[List[str], List[str], str]:
    """
    Run command for the detected application entry point.

    Returns ``(steps, gaps, entry_directory)``.  *entry_directory* is the
    directory of the entry point, or "" when none was detected, so the caller
    can tell a server package from a separate frontend package.

    When no entry point was detected the "not detected" statement is returned
    as a *step* — but only if the caller already has other steps to show.  With
    no other signal at all the whole guide collapses to ``_NOT_DETECTED``,
    which is more honest than listing one thing we could not find.
    """
    steps: List[str] = []
    gaps: List[str] = []
    files = _detected_files(analysis)

    entries = _detected_entry_points(analysis)
    if not entries:
        if not any(_basename(p).lower() == "package.json" for p in files):
            steps.append(_NO_ENTRY_POINT_STEP)
        return steps, gaps, ""

    entry_dir = _dir_of(entries[0])
    command, caveat = _start_command(analysis, entries[0])
    if command:
        steps.append(command)
    if caveat:
        gaps.append(caveat)
    return steps, gaps, entry_dir


def _fallback_setup_guide(analysis: RepoAnalysis) -> Tuple[List[str], List[str]]:
    """
    Grounded "get it running" steps.

    Every command references a file path the analyzer actually reported, or an
    entry point it actually listed.  Anything the analyzer could not determine
    is returned in *gaps* so the caller can state it rather than guess.

    Returns ``(steps, gaps)``.  When no step can be grounded at all, *steps* is
    a single ``_NOT_DETECTED`` sentinel so the UI never renders an empty list.
    """
    steps: List[str] = []
    gaps: List[str] = []

    # 1. Install dependencies, from the manifests that were reported.
    install_steps, install_gaps = _install_steps(analysis)
    steps.extend(install_steps)
    gaps.extend(install_gaps)

    # 2. Configure the environment from the detected template.
    env_steps, env_gaps = _env_config_steps(analysis)
    steps.extend(env_steps)
    gaps.extend(env_gaps)

    # 3. Start the detected application entry point.  The "not detected"
    #    statement is dropped when nothing else was found — a guide made of a
    #    single "we could not find anything" line is less useful than the
    #    _NOT_DETECTED sentinel, which says the same thing in one place.
    start_steps, start_gaps, entry_dir = _application_start_steps(analysis)
    if start_steps == [_NO_ENTRY_POINT_STEP] and not steps:
        start_steps = []
    steps.extend(start_steps)
    gaps.extend(start_gaps)

    # 4. Start the frontend dev server, when it is a separate package.
    node_start, node_start_gaps = _node_start_steps(analysis, entry_dir)
    steps.extend(node_start)
    gaps.extend(node_start_gaps)

    # 5. Build the container image, when a container definition was detected.
    docker_step = _docker_build_step(analysis)
    if docker_step:
        steps.append(docker_step)

    if not steps:
        return [_NOT_DETECTED], gaps

    return steps, gaps


def _fallback_workflow(analysis: RepoAnalysis) -> List[str]:
    """
    Grounded day-to-day development loop.

    Built from the same detected-file signals as ``_fallback_setup_guide`` —
    start commands first because they are what a developer repeats all day —
    plus the verify-while-you-work steps (tests, CI, task runners).  Every entry
    is conditional on a concrete signal in the input; nothing is invented.  If
    no signals are present at all, the sentinel is returned so callers always
    receive a non-empty list.
    """
    setup_steps, setup_gaps = _fallback_setup_guide(analysis)
    if setup_steps == [_NOT_DETECTED]:
        return [_NOT_DETECTED]

    steps: List[str] = []
    gaps: List[str] = []
    files = _detected_files(analysis)

    # The repeat-every-day commands first.  A "not detected" start statement is
    # only meaningful once the caller knows the project itself was detected —
    # which the sentinel early-return above has already established.
    start_steps, start_gaps, entry_dir = _application_start_steps(analysis)
    steps.extend(start_steps)
    gaps.extend(start_gaps)

    node_start, node_start_gaps = _node_start_steps(analysis, entry_dir)
    steps.extend(node_start)
    gaps.extend(node_start_gaps)

    # Then the one-off setup, so a new joiner has the full picture in order.
    install_steps, install_gaps = _install_steps(analysis)
    steps.extend(install_steps)
    gaps.extend(install_gaps)

    env_steps, env_gaps = _env_config_steps(analysis)
    steps.extend(env_steps)
    gaps.extend(env_gaps)

    docker_step = _docker_build_step(analysis)
    if docker_step:
        steps.append(docker_step)

    # Verify the change.
    test_step = _test_run_step(analysis)
    if test_step:
        steps.append(test_step)

    if _structure_flag(analysis, "has_ci"):
        steps.append(
            "CI configuration was detected — run your change through the same "
            "pipeline the repository uses before opening a pull request."
        )

    for task_runner in (p for p in files if _basename(p).lower() in {"makefile", "justfile"}):
        runner = _basename(task_runner)
        steps.append(
            f"{_run_in(_dir_of(task_runner), runner)} <target>  # the available "
            f"targets in '{_posix(task_runner)}' were not detected"
        )

    # Explicitly state what could not be determined instead of inventing it.
    seen: set = set()
    for gap in [*start_gaps, *node_start_gaps, *install_gaps, *env_gaps, *setup_gaps]:
        if gap not in seen:
            seen.add(gap)
            steps.append(f"Not detected: {gap}.")

    return steps


def _fallback_generate(analysis: RepoAnalysis) -> OnboardingKnowledge:
    notes: List[str] = []

    if analysis.project_name:
        overview = _fallback_overview(analysis)
    else:
        overview = _fallback_overview(analysis)
        notes.append("project_name unavailable")

    tech_stack: List[TechStackItem] = []
    for lang in analysis.languages:
        tech_stack.append(TechStackItem(name=lang, category="language", role="Used in this project."))
    for fw in analysis.frameworks:
        tech_stack.append(TechStackItem(name=fw, category="framework", role="Used in this project."))
    if not tech_stack:
        notes.append("languages/frameworks unavailable")

    important_files = [_file_to_explanation(f) for f in analysis.important_files]
    if not important_files:
        notes.append("important_files unavailable")

    dependencies = [_dep_to_explanation(d) for d in analysis.dependencies]
    if not dependencies:
        notes.append("dependencies unavailable")

    setup_guide, setup_gaps = _fallback_setup_guide(analysis)
    notes.extend(f"setup_guide: {gap}" for gap in setup_gaps)

    # The fallback path cannot generate prose architecture from project_structure
    # (that requires the LLM). Note this honestly whether or not the field is present.
    notes.append(
        "architecture: prose description unavailable in fallback mode — "
        "see architecture_diagram for a deterministic view, or enable the LLM path."
    )
    if analysis.project_structure is None:
        notes.append("project_structure unavailable")

    return OnboardingKnowledge(
        project_overview=overview,
        tech_stack=tech_stack,
        architecture=(
            "Architecture prose unavailable in fallback mode — "
            "see architecture_diagram for a deterministic structural view."
        ),
        important_files=important_files,
        dependencies=dependencies,
        setup_guide=setup_guide,
        development_workflow=_fallback_workflow(analysis),
        starter_tasks=_fallback_starter_tasks(analysis),
        architecture_diagram=generate_architecture_diagram(analysis),
        data_completeness_notes=notes,
        used_llm=False,
    )


# ---------------------------------------------------------------------------
# LLM path (synchronous)
# ---------------------------------------------------------------------------

def _llm_generate(
    analysis: RepoAnalysis, request_id: str = ""
) -> OnboardingKnowledge:
    """Call the LLM synchronously and return a validated OnboardingKnowledge."""
    # Scrub any secret-looking strings before they leave this process.
    sanitize_result = sanitize_analysis(analysis)
    if sanitize_result.had_redactions:
        log.warning(
            "ai.sanitize: %d field(s) redacted before LLM call",
            len(sanitize_result.redactions),
            extra={
                "json_fields": {
                    "event": "ai.sanitize.redactions",
                    "request_id": request_id,
                    "redaction_count": len(sanitize_result.redactions),
                    # Log WHAT was redacted (field paths + pattern names) but never the values.
                    "redactions": sanitize_result.redactions,
                }
            },
        )
    clean_analysis = sanitize_result.analysis

    t0 = time.monotonic()
    user_prompt = build_user_prompt(clean_analysis)
    # call_llm now returns a structured dict via tool-use — no JSON parsing needed.
    data: Dict[str, Any] = call_llm(SYSTEM_PROMPT, user_prompt)
    llm_ms = (time.monotonic() - t0) * 1000

    diagram = generate_architecture_diagram(analysis)
    data["architecture_diagram"] = diagram
    data["used_llm"] = True

    # If the diagram itself signals "no architecture detectable", make sure
    # data_completeness_notes reflects that even if the LLM didn't add it.
    if _DIAGRAM_UNKNOWN_SENTINEL in diagram:
        notes = data.get("data_completeness_notes") or []
        marker = "architecture_diagram: no structural signals detected"
        if marker not in notes:
            notes.append(marker)
        data["data_completeness_notes"] = notes

    result = OnboardingKnowledge.model_validate(data)

    # Ground the audit against the *original* (unsanitized) analysis so that
    # redacted fields don't generate spurious grounding failures.
    audit_failures = _grounding_audit_failures(result, analysis)
    log.info(
        "ai.llm_generate completed",
        extra={
            "json_fields": {
                "event": "ai.llm_generate.ok",
                "request_id": request_id,
                "llm_latency_ms": round(llm_ms, 1),
                "prompt_version": PROMPT_VERSION,
                "grounding_audit_failures": audit_failures,
                "grounding_audit_failure_count": len(audit_failures),
            }
        },
    )
    if audit_failures:
        log.warning(
            "ai.grounding_audit: %d potential hallucination(s) detected in LLM output",
            len(audit_failures),
            extra={
                "json_fields": {
                    "event": "ai.grounding_audit.failures",
                    "request_id": request_id,
                    "failures": audit_failures,
                }
            },
        )

    return result


# ---------------------------------------------------------------------------
# LLM path (asynchronous)
# ---------------------------------------------------------------------------

async def _async_llm_generate(
    analysis: RepoAnalysis, request_id: str = ""
) -> OnboardingKnowledge:
    """Call the LLM asynchronously and return a validated OnboardingKnowledge."""
    # Scrub any secret-looking strings before they leave this process.
    sanitize_result = sanitize_analysis(analysis)
    if sanitize_result.had_redactions:
        log.warning(
            "ai.sanitize: %d field(s) redacted before LLM call",
            len(sanitize_result.redactions),
            extra={
                "json_fields": {
                    "event": "ai.sanitize.redactions",
                    "request_id": request_id,
                    "redaction_count": len(sanitize_result.redactions),
                    "redactions": sanitize_result.redactions,
                }
            },
        )
    clean_analysis = sanitize_result.analysis

    t0 = time.monotonic()
    user_prompt = build_user_prompt(clean_analysis)
    data: Dict[str, Any] = await acall_llm(SYSTEM_PROMPT, user_prompt)
    llm_ms = (time.monotonic() - t0) * 1000

    diagram = generate_architecture_diagram(analysis)
    data["architecture_diagram"] = diagram
    data["used_llm"] = True

    if _DIAGRAM_UNKNOWN_SENTINEL in diagram:
        notes = data.get("data_completeness_notes") or []
        marker = "architecture_diagram: no structural signals detected"
        if marker not in notes:
            notes.append(marker)
        data["data_completeness_notes"] = notes

    result = OnboardingKnowledge.model_validate(data)

    audit_failures = _grounding_audit_failures(result, analysis)
    log.info(
        "ai.async_llm_generate completed",
        extra={
            "json_fields": {
                "event": "ai.llm_generate.ok",
                "request_id": request_id,
                "llm_latency_ms": round(llm_ms, 1),
                "prompt_version": PROMPT_VERSION,
                "grounding_audit_failures": audit_failures,
                "grounding_audit_failure_count": len(audit_failures),
            }
        },
    )
    if audit_failures:
        log.warning(
            "ai.grounding_audit: %d potential hallucination(s) detected in LLM output",
            len(audit_failures),
            extra={
                "json_fields": {
                    "event": "ai.grounding_audit.failures",
                    "request_id": request_id,
                    "failures": audit_failures,
                }
            },
        )

    return result


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def generate_onboarding(
    analysis: RepoAnalysis,
    use_llm: bool = True,
    _request_id: str = "",
) -> OnboardingKnowledge:
    """
    Synchronous entry point.  Checks the in-memory cache first; falls back to
    the rule-based path if the LLM call fails for any reason.
    """
    if use_llm:
        key = _cache_key(analysis)
        cached = _cache_get(key)
        if cached is not None:
            log.info(
                "ai.cache_hit",
                extra={
                    "json_fields": {
                        "event": "ai.cache_hit",
                        "request_id": _request_id,
                        "hash_prefix": key[:12],
                    }
                },
            )
            ai_metrics.record(path="cache_hit", latency_ms=0.0)
            return cached

        # Check cost budget *after* the cache — cache hits are free.
        if not _budget_check():
            return _fallback_generate(analysis)

        try:
            result = _llm_generate(analysis, request_id=_request_id)
            _cache_set(key, result)
            return result
        except Exception as exc:
            # Broad catch is intentional — reliability safety net.
            # Use type(exc).__name__ not repr(exc) to avoid leaking key material
            # if the exception message ever contains env-var content.
            log.warning(
                "ai.llm_fallback: LLM path failed (%s); using rule-based fallback.",
                type(exc).__name__,
                extra={
                    "json_fields": {
                        "event": "ai.llm_fallback",
                        "request_id": _request_id,
                        "error_type": type(exc).__name__,
                        # Message is safe for LLMUnavailableError (controlled text);
                        # for other exceptions we log the type only.
                        "error_msg": str(exc) if isinstance(exc, LLMUnavailableError) else "(suppressed)",
                    }
                },
            )
    return _fallback_generate(analysis)


async def async_generate_onboarding(
    analysis: RepoAnalysis,
    use_llm: bool = True,
    _request_id: str = "",
) -> OnboardingKnowledge:
    """
    Async entry point for use from ``async def`` FastAPI route handlers.
    Checks the in-memory cache first; falls back to the rule-based path if
    the LLM call fails for any reason.
    """
    if use_llm:
        key = _cache_key(analysis)
        cached = _cache_get(key)
        if cached is not None:
            log.info(
                "ai.cache_hit",
                extra={
                    "json_fields": {
                        "event": "ai.cache_hit",
                        "request_id": _request_id,
                        "hash_prefix": key[:12],
                    }
                },
            )
            ai_metrics.record(path="cache_hit", latency_ms=0.0)
            return cached

        # Check cost budget *after* the cache — cache hits are free.
        if not _budget_check():
            return _fallback_generate(analysis)

        try:
            result = await _async_llm_generate(analysis, request_id=_request_id)
            _cache_set(key, result)
            return result
        except Exception as exc:
            log.warning(
                "ai.llm_fallback: LLM path failed (%s); using rule-based fallback.",
                type(exc).__name__,
                extra={
                    "json_fields": {
                        "event": "ai.llm_fallback",
                        "request_id": _request_id,
                        "error_type": type(exc).__name__,
                        "error_msg": str(exc) if isinstance(exc, LLMUnavailableError) else "(suppressed)",
                    }
                },
            )
    return _fallback_generate(analysis)
