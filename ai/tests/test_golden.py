"""
Golden-dataset regression tests.

These tests assert key structural properties of generate_onboarding() outputs
across a range of diverse RepoAnalysis inputs, all in offline mode (no API key).

The golden dataset covers:
  1. A Python/FastAPI backend-only project
  2. A Node.js / Next.js full-stack project
  3. A Go + Postgres microservice
  4. A sparse / almost-empty analysis (edge case)
  5. Unicode and special-character paths + names

For each fixture we assert:
  - No sentinel strings appear where data was available
  - No tech_stack / dep names were invented that aren't in the input
  - schema_version is present
  - Diagram nodes match detected signals
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai.generator import _grounding_audit_failures, generate_onboarding
from ai.schemas import DependencyEntry, ImportantFileEntry, RepoAnalysis

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOLDEN_PYTHON_BACKEND = RepoAnalysis(
    project_name="my-api",
    languages=["Python"],
    frameworks=["FastAPI"],
    important_files=[
        ImportantFileEntry(path="main.py", description="App entry point"),
        ImportantFileEntry(path="models.py", description="SQLAlchemy ORM models"),
    ],
    dependencies=[
        DependencyEntry(name="fastapi", version="0.115.0", type="prod"),
        DependencyEntry(name="sqlalchemy", version="2.0.0", type="prod"),
        DependencyEntry(name="uvicorn", type="prod"),
    ],
    project_structure={"src": ["main.py", "models.py"]},
)

GOLDEN_NEXTJS_FULLSTACK = RepoAnalysis(
    project_name="storefront",
    languages=["TypeScript"],
    frameworks=["Next.js", "React"],
    important_files=[
        ImportantFileEntry(path="pages/index.tsx", description="Home page"),
        ImportantFileEntry(path="pages/api/products.ts", description="Product API route"),
    ],
    dependencies=[
        DependencyEntry(name="next", version="14.0.0", type="prod"),
        DependencyEntry(name="react", version="18.0.0", type="prod"),
        DependencyEntry(name="stripe", version="12.0.0", type="prod"),
        DependencyEntry(name="prisma", version="5.0.0", type="prod"),
    ],
    project_structure={"pages": ["index.tsx", "api/products.ts"]},
)

GOLDEN_GO_MICROSERVICE = RepoAnalysis(
    project_name="inventory-svc",
    languages=["Go"],
    frameworks=["Gin"],
    important_files=[
        ImportantFileEntry(path="cmd/server/main.go", description="Entry point"),
        ImportantFileEntry(path="internal/handler/item.go", description="Item HTTP handlers"),
    ],
    dependencies=[
        DependencyEntry(name="gin", type="prod"),
        DependencyEntry(name="postgres", type="prod"),
        DependencyEntry(name="kafka", type="prod"),
    ],
    project_structure={"cmd": ["server/main.go"], "internal": ["handler/item.go"]},
)

GOLDEN_SPARSE = RepoAnalysis(
    # Minimal info — only a project name
    project_name="mystery-service",
    languages=[],
    frameworks=[],
    important_files=[],
    dependencies=[],
    project_structure=None,
)

# Unicode paths, emoji in description, non-ASCII dep names
GOLDEN_UNICODE = RepoAnalysis(
    project_name="プロジェクト",                # Japanese
    languages=["Python", "TypeScript"],
    frameworks=["Django"],
    important_files=[
        ImportantFileEntry(
            path="src/données/modèles.py",       # French accents
            description="Modèles de données 🗃️",
        ),
        ImportantFileEntry(
            path="tests/тест.py",                # Cyrillic
            description="Unit tests",
        ),
    ],
    dependencies=[
        DependencyEntry(name="django", version="4.2.0", type="prod"),
        DependencyEntry(name="djangorestframework", type="prod"),
    ],
)


# ---------------------------------------------------------------------------
# 1. Python / FastAPI backend-only
# ---------------------------------------------------------------------------

def test_golden_python_backend_no_gaps():
    result = generate_onboarding(GOLDEN_PYTHON_BACKEND, use_llm=False)
    assert "my-api" in result.project_overview
    assert result.used_llm is False
    assert result.schema_version == 1
    tech_names = {t.name for t in result.tech_stack}
    assert "FastAPI" in tech_names
    assert "Python" in tech_names
    # Dependencies present → setup_guide must not be the sentinel
    assert result.setup_guide != ["Not derivable from the provided analysis data."]
    # Files present → important_files must be non-empty
    assert len(result.important_files) == 2


def test_golden_python_backend_diagram_has_backend():
    result = generate_onboarding(GOLDEN_PYTHON_BACKEND, use_llm=False)
    assert "Backend" in result.architecture_diagram
    # SQLAlchemy → database signal
    assert "Database" in result.architecture_diagram


def test_golden_python_backend_grounding():
    """Fallback output must not invent names."""
    result = generate_onboarding(GOLDEN_PYTHON_BACKEND, use_llm=False)
    failures = _grounding_audit_failures(result, GOLDEN_PYTHON_BACKEND)
    assert failures == [], f"Grounding failures in fallback output: {failures}"


# ---------------------------------------------------------------------------
# 2. Next.js full-stack
# ---------------------------------------------------------------------------

def test_golden_nextjs_diagram_has_frontend_and_db():
    result = generate_onboarding(GOLDEN_NEXTJS_FULLSTACK, use_llm=False)
    assert "Frontend" in result.architecture_diagram   # next / react → frontend
    assert "Database" in result.architecture_diagram   # prisma → database
    assert "Stripe" in result.architecture_diagram
    # Next.js is classified as frontend (not a backend framework); the diagram
    # correctly shows a frontend + db topology for a Next.js + Prisma stack.


def test_golden_nextjs_tech_stack():
    result = generate_onboarding(GOLDEN_NEXTJS_FULLSTACK, use_llm=False)
    tech_names = {t.name for t in result.tech_stack}
    assert "Next.js" in tech_names or "React" in tech_names


# ---------------------------------------------------------------------------
# 3. Go + Postgres microservice
# ---------------------------------------------------------------------------

def test_golden_go_microservice_diagram():
    result = generate_onboarding(GOLDEN_GO_MICROSERVICE, use_llm=False)
    assert "Backend" in result.architecture_diagram     # gin
    assert "Database" in result.architecture_diagram    # postgres
    assert "Kafka" in result.architecture_diagram


def test_golden_go_microservice_grounding():
    result = generate_onboarding(GOLDEN_GO_MICROSERVICE, use_llm=False)
    failures = _grounding_audit_failures(result, GOLDEN_GO_MICROSERVICE)
    assert failures == [], f"Grounding failures: {failures}"


# ---------------------------------------------------------------------------
# 4. Sparse analysis
# ---------------------------------------------------------------------------

def test_golden_sparse_completeness_notes():
    result = generate_onboarding(GOLDEN_SPARSE, use_llm=False)
    # All unavailable items must be noted
    assert "important_files unavailable" in result.data_completeness_notes
    assert "dependencies unavailable" in result.data_completeness_notes
    assert "languages/frameworks unavailable" in result.data_completeness_notes
    assert any("architecture" in n for n in result.data_completeness_notes)


def test_golden_sparse_diagram_unknown():
    result = generate_onboarding(GOLDEN_SPARSE, use_llm=False)
    assert "Architecture not determinable from available data" in result.architecture_diagram


def test_golden_sparse_setup_guide_sentinel():
    result = generate_onboarding(GOLDEN_SPARSE, use_llm=False)
    assert result.setup_guide == ["Not derivable from the provided analysis data."]


# ---------------------------------------------------------------------------
# 5. Unicode paths and names
# ---------------------------------------------------------------------------

def test_golden_unicode_survives_validation():
    """RepoAnalysis with unicode paths/names must pass Pydantic validation."""
    result = generate_onboarding(GOLDEN_UNICODE, use_llm=False)
    assert result.schema_version == 1


def test_golden_unicode_project_name_in_overview():
    result = generate_onboarding(GOLDEN_UNICODE, use_llm=False)
    assert "プロジェクト" in result.project_overview


def test_golden_unicode_files_preserved():
    result = generate_onboarding(GOLDEN_UNICODE, use_llm=False)
    paths = {f.path for f in result.important_files}
    assert "src/données/modèles.py" in paths
    assert "tests/тест.py" in paths


def test_golden_unicode_diagram_has_backend():
    result = generate_onboarding(GOLDEN_UNICODE, use_llm=False)
    assert "Backend" in result.architecture_diagram   # django
    assert "Database" not in result.architecture_diagram  # no DB dep in fixture


def test_golden_unicode_grounding():
    result = generate_onboarding(GOLDEN_UNICODE, use_llm=False)
    failures = _grounding_audit_failures(result, GOLDEN_UNICODE)
    assert failures == [], f"Grounding failures with unicode input: {failures}"
