"""
Basic sanity tests. Run with: python -m pytest ai/tests/

These force use_llm=False so they run offline / without an API key —
they check the grounded fallback logic, which is the part that must
never hallucinate.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai.generator import _dep_name, _dep_to_explanation, _file_to_explanation, _strip_json_fences, generate_onboarding
from ai.mock_data import MOCK_ANALYSIS_COMPLETE, MOCK_ANALYSIS_SPARSE
from ai.schemas import DependencyEntry, ImportantFileEntry, RepoAnalysis


def test_complete_analysis_produces_grounded_output():
    result = generate_onboarding(MOCK_ANALYSIS_COMPLETE, use_llm=False)
    assert "developer-onboarding-assistant" in result.project_overview
    names = {item.name for item in result.tech_stack}
    assert "FastAPI" in names and "Python" in names
    assert any(f.path == "backend/main.py" for f in result.important_files)
    assert "Frontend" in result.architecture_diagram
    assert "Backend" in result.architecture_diagram
    # anthropic dep triggers the external-service node in the diagram
    assert "Anthropic" in result.architecture_diagram


def test_sparse_analysis_reports_gaps_instead_of_inventing():
    result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    assert "important_files unavailable" in result.data_completeness_notes
    assert "dependencies unavailable" in result.data_completeness_notes
    assert result.important_files == []
    assert result.dependencies == []


def test_fallback_always_notes_architecture_limitation():
    """Fallback can't write architecture prose — must note this in data_completeness_notes."""
    for analysis in (MOCK_ANALYSIS_COMPLETE, MOCK_ANALYSIS_SPARSE):
        result = generate_onboarding(analysis, use_llm=False)
        assert any("architecture" in note for note in result.data_completeness_notes), (
            f"Expected architecture note in data_completeness_notes, got: {result.data_completeness_notes}"
        )
        assert "fallback" in result.architecture.lower(), (
            f"architecture field should reference fallback mode, got: {result.architecture}"
        )


# --- Hallucination-fix regression tests ---

def test_setup_guide_with_deps_names_them_explicitly():
    """setup_guide must list actual dependency names, not generic prose."""
    result = generate_onboarding(MOCK_ANALYSIS_COMPLETE, use_llm=False)
    # The first step must contain at least one real dep name from the mock data.
    assert any(
        "fastapi" in step.lower() or "uvicorn" in step.lower() or "pydantic" in step.lower()
        for step in result.setup_guide
    ), f"setup_guide did not mention any known dep names: {result.setup_guide}"


def test_setup_guide_sentinel_when_no_deps():
    """When dependencies is empty the fallback must emit the sentinel, not generic steps."""
    result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    assert result.setup_guide == ["Not derivable from the provided analysis data."], (
        f"Expected sentinel for sparse input, got: {result.setup_guide}"
    )


def test_development_workflow_is_always_sentinel_in_fallback():
    """Fallback must never invent workflow steps — always the sentinel string."""
    for analysis in (MOCK_ANALYSIS_COMPLETE, MOCK_ANALYSIS_SPARSE):
        result = generate_onboarding(analysis, use_llm=False)
        assert result.development_workflow == ["Not derivable from the provided analysis data."], (
            f"development_workflow was not the sentinel: {result.development_workflow}"
        )


# --- Fix 3: plain-string Union branch tests ---

def test_file_to_explanation_plain_string():
    """_file_to_explanation must handle a bare string path, not just ImportantFileEntry."""
    result = _file_to_explanation("src/main.py")
    assert result.path == "src/main.py"
    assert result.purpose == "Purpose not specified by analyzer."


def test_file_to_explanation_entry_with_description():
    entry = ImportantFileEntry(path="src/app.py", description="App entry point.")
    result = _file_to_explanation(entry)
    assert result.path == "src/app.py"
    assert result.purpose == "App entry point."


def test_dep_to_explanation_plain_string():
    """_dep_to_explanation must handle a bare string name, not just DependencyEntry."""
    result = _dep_to_explanation("requests")
    assert result.name == "requests"
    assert result.purpose == "Purpose not specified by analyzer."


def test_dep_name_plain_string():
    assert _dep_name("flask") == "flask"
    assert _dep_name(DependencyEntry(name="flask", version="3.0.0")) == "flask"


def test_plain_string_deps_flow_through_fallback():
    """Plain-string deps in RepoAnalysis must appear in setup_guide and dependencies."""
    analysis = RepoAnalysis(project_name="test", languages=["Python"], dependencies=["requests", "click"])
    result = generate_onboarding(analysis, use_llm=False)
    dep_names = {d.name for d in result.dependencies}
    assert dep_names == {"requests", "click"}
    assert "requests" in result.setup_guide[0]
    assert "click" in result.setup_guide[0]


# --- Fix 4: _strip_json_fences robustness ---

def test_strip_json_fences_clean_json():
    raw = '{"key": "value"}'
    assert _strip_json_fences(raw) == raw


def test_strip_json_fences_with_json_prefix():
    raw = "```json\n{\"key\": \"value\"}\n```"
    assert _strip_json_fences(raw) == '{"key": "value"}'


def test_strip_json_fences_trailing_newline_before_fence():
    """Claude sometimes emits a trailing newline before the closing fence."""
    raw = "```json\n{\"key\": \"value\"}\n```\n"
    assert _strip_json_fences(raw) == '{"key": "value"}'


def test_strip_json_fences_plain_fence():
    raw = "```\n{\"key\": \"value\"}\n```"
    assert _strip_json_fences(raw) == '{"key": "value"}'


# --- Fix 5: used_llm field ---

def test_fallback_sets_used_llm_false():
    result = generate_onboarding(MOCK_ANALYSIS_COMPLETE, use_llm=False)
    assert result.used_llm is False


def test_fallback_sparse_sets_used_llm_false():
    result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    assert result.used_llm is False


if __name__ == "__main__":
    test_complete_analysis_produces_grounded_output()
    test_sparse_analysis_reports_gaps_instead_of_inventing()
    test_fallback_always_notes_architecture_limitation()
    test_setup_guide_with_deps_names_them_explicitly()
    test_setup_guide_sentinel_when_no_deps()
    test_development_workflow_is_always_sentinel_in_fallback()
    test_file_to_explanation_plain_string()
    test_file_to_explanation_entry_with_description()
    test_dep_to_explanation_plain_string()
    test_dep_name_plain_string()
    test_plain_string_deps_flow_through_fallback()
    test_strip_json_fences_clean_json()
    test_strip_json_fences_with_json_prefix()
    test_strip_json_fences_trailing_newline_before_fence()
    test_strip_json_fences_plain_fence()
    test_fallback_sets_used_llm_false()
    test_fallback_sparse_sets_used_llm_false()
    print("All tests passed.")
