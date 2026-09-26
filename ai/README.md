# AI Analysis + Architecture Layer

Owner: Radhika. Turns Meith's Repository Analyzer output into onboarding
knowledge for a new developer, and hands it to Kushal's backend / Mayank's
frontend as one structured JSON object.

## Files

| File | Purpose |
|---|---|
| `schemas.py` | Input contract (`RepoAnalysis`) and output contract (`OnboardingKnowledge`) |
| `prompts.py` | System + user prompt, constrained to only use analyzer data |
| `llm_client.py` | Thin Anthropic API wrapper |
| `generator.py` | Orchestrator — tries the LLM, falls back to a grounded rule-based path if no API key / call fails |
| `diagram.py` | Deterministic Mermaid diagram builder (not LLM-generated, to avoid hallucinated architecture) |
| `router.py` | FastAPI router — one import away from being wired into `backend/main.py` |
| `mock_data.py` | Sample analyzer outputs (complete + sparse) for testing before Meith's analyzer exists |
| `tests/test_generator.py` | Offline sanity tests (no API key needed) |

## Status of the actual repo (as of this build)

Only `backend/` exists right now — Meith's analyzer and Mayank's frontend
haven't been pushed yet. Everything here is built against the schema in the
task brief (`project_name, languages, frameworks, important_files,
dependencies, project_structure`) plus mock data, so it's ready to plug in
the moment the real analyzer lands. **Nothing in `backend/` was modified.**

## How Kushal integrates this (2 lines, when ready)

```python
# backend/main.py
from ai.router import router as ai_router
app.include_router(ai_router)
```

That exposes `POST /ai/generate`, which accepts a `RepoAnalysis` JSON body and
returns an `OnboardingKnowledge` JSON body — matching the schema in the task
brief, plus one extra field: `data_completeness_notes` (see below).

## How Mayank's frontend uses it

Call `POST /ai/generate` with the analyzer's JSON, render the returned fields
directly. `architecture_diagram` is plain Mermaid text — pass it to any
Mermaid renderer. If `data_completeness_notes` is non-empty, show those as
"not available" hints instead of leaving sections blank/misleading.

## Environment

```bash
pip install anthropic   # add to backend/requirements.txt when wiring in
export ANTHROPIC_API_KEY=sk-...
```

Without the key set, `generate_onboarding()` automatically uses the
rule-based fallback — the demo still works, just with plainer prose.

## Design decisions worth noting for judges / Bob usage log

- **Diagram is never LLM-generated.** `diagram.py` only draws nodes/edges it
  has direct evidence for (detected frameworks/dependencies). This was a
  hallucination risk identified early — free-text diagram generation is where
  models most readily invent connections that "look right."
- **Every output field traces back to input data or an explicit "unavailable"
  note.** The prompt (`prompts.py`) forces this, and the fallback path
  (`generator.py::_fallback_generate`) enforces it mechanically as a backstop
  if the LLM path fails or isn't configured.
- **Fallback path exists so the team is never blocked by API access during
  the demo.** This was worth calling out as a reliability decision.

Recommended log entries for `bob_sessions/` (once that folder exists): prompt
design iterations for `prompts.py`, the decision to keep diagram generation
deterministic, and review of `generator.py`'s fallback logic.

## Running tests

```bash
python -m pytest ai/tests/
# or, without pytest installed:
python ai/tests/test_generator.py
```
