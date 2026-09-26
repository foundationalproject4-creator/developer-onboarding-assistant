"""
Basic sanity tests. Run with: python -m pytest ai/tests/

These force use_llm=False so they run offline / without an API key —
they check the grounded fallback logic, which is the part that must
never hallucinate.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai.generator import generate_onboarding
from ai.mock_data import MOCK_ANALYSIS_COMPLETE, MOCK_ANALYSIS_SPARSE


def test_complete_analysis_produces_grounded_output():
    result = generate_onboarding(MOCK_ANALYSIS_COMPLETE, use_llm=False)
    assert "developer-onboarding-assistant" in result.project_overview
    names = {item.name for item in result.tech_stack}
    assert "FastAPI" in names and "Python" in names
    assert any(f.path == "backend/main.py" for f in result.important_files)
    assert "Frontend" in result.architecture_diagram
    assert "Backend" in result.architecture_diagram


def test_sparse_analysis_reports_gaps_instead_of_inventing():
    result = generate_onboarding(MOCK_ANALYSIS_SPARSE, use_llm=False)
    assert "important_files unavailable" in result.data_completeness_notes
    assert "dependencies unavailable" in result.data_completeness_notes
    assert result.important_files == []
    assert result.dependencies == []


if __name__ == "__main__":
    test_complete_analysis_produces_grounded_output()
    test_sparse_analysis_reports_gaps_instead_of_inventing()
    print("All tests passed.")
