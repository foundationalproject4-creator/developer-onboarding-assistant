# AI Analysis + Architecture Layer

Owner: Radhika. Turns Meith's Repository Analyzer output into onboarding
knowledge for a new developer, and hands it to Kushal's backend / Mayank's
frontend as one structured JSON object.

## Files

| File | Purpose |
|---|---|
| `schemas.py` | Input contract (`RepoAnalysis`) and output contract (`OnboardingKnowledge`) |
| `prompts.py` | System + user prompt, constrained to only use analyzer data |
| `llm_client.py` | Thin Anthropic API wrapper (tool-use, retry, timeout, async) |
| `generator.py` | Orchestrator — sanitizes input, tries LLM (with budget cap), falls back to rule-based path |
| `sanitize.py` | Pre-send scrubber — redacts secret-looking strings before they reach the LLM |
| `metrics.py` | In-process counters: LLM success rate, fallback rate, latency, fallback alert |
| `diagram.py` | Deterministic Mermaid diagram builder (not LLM-generated, to avoid hallucinated architecture) |
| `router.py` | FastAPI router — one import away from being wired into `backend/main.py` |
| `mock_data.py` | Sample analyzer outputs (complete + sparse) for testing before Meith's analyzer exists |
| `tests/test_generator.py` | Core offline tests (no API key needed) |
| `tests/test_golden.py` | Golden-dataset regression suite (5 diverse fixtures) |
| `tests/test_grounding.py` | Grounding audit tests (mocked LLM, verifies hallucination detection) |
| `tests/test_security.py` | Input validation, prompt injection, secret safety, and metrics tests |

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
returns an `OnboardingKnowledge` JSON body.  Check `data_completeness_notes`
for any fields that could not be derived from the input.

## How Mayank's frontend uses it

Call `POST /ai/generate` with the analyzer's JSON, render the returned fields
directly. `architecture_diagram` is plain Mermaid text — pass it to any
Mermaid renderer. If `data_completeness_notes` is non-empty, show those as
"not available" hints instead of leaving sections blank/misleading.

---

### ⚠️ Note for Mayank — `used_llm` UX (human decision required)

The `OnboardingKnowledge` response includes a boolean field `used_llm`:

- `used_llm = true` → the Anthropic LLM ran successfully; the prose is
  AI-generated and grounded in the repo data.
- `used_llm = false` → the rule-based fallback was used (no API key, LLM
  error, or budget cap hit); the output is structurally correct but the
  prose is minimal/templated.

**The frontend should surface this difference clearly to the user.**  The
exact UX is a product decision for Mayank/the team, but here are the options
to consider:

1. **Badge approach** — show an "AI-enhanced" badge when `used_llm=true`,
   and a "Basic analysis" badge when `used_llm=false`.  Simple, low visual
   noise.
2. **Banner approach** — show a dismissible info banner at the top of the
   onboarding page when `used_llm=false`, e.g.:
   *"This analysis was generated without AI assistance. Connect an
   Anthropic API key for richer explanations."*
3. **Inline indicators** — grey out or reduce the visual weight of sections
   that contain sentinel strings ("Not derivable from the provided analysis
   data."), regardless of `used_llm`.

A combination of options 1 + 3 is recommended.  Do NOT silently show the
sentinel strings as normal content — a new developer who reads
"Not derivable from the provided analysis data." in the setup guide will be
confused rather than helped.

This is flagged here rather than implemented in code because it is a UX
and product decision, not a technical one.

---

## Data privacy & third-party LLM notice

> **⚠️ Privacy notice — read before enabling the LLM path in production.**

When `ANTHROPIC_API_KEY` is set, the following data from the `RepoAnalysis`
payload is sent to the **Anthropic Messages API** (a third-party service):

- `project_name`
- `languages`, `frameworks`
- `important_files` (paths and descriptions)
- `dependencies` (names and versions)
- `project_structure` (file tree / path list)

This data is sent to Anthropic's servers and processed according to
[Anthropic's privacy policy and data handling terms](https://www.anthropic.com/legal/privacy).

**Before enabling the LLM path on a private or proprietary repository, the
team/product owner must review whether this data handling is acceptable under
the project's data-handling policy, any applicable NDAs, and relevant data
protection regulations (GDPR, CCPA, etc.).**

Mitigations already in place:
- `sanitize.py` redacts strings that match common API key / credential
  patterns before data is sent (best-effort — not a substitute for policy
  review).
- `schemas.py` enforces size limits on all fields, bounding how much data
  can be sent per request.

**This is a decision for the team/product owner, not something that can be
auto-resolved in code.**  If the decision is "do not send to Anthropic", set
`AI_MAX_REQUESTS=0` or do not set `ANTHROPIC_API_KEY` — the fallback path
runs entirely locally and sends nothing to any third party.

---

## Environment variables

Copy `.env.example` to `.env` and fill in values.  Required variables:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...   # Required for LLM path
AI_MAX_REQUESTS=0                    # 0 = unlimited; set >0 to cap LLM calls
```

Without `ANTHROPIC_API_KEY`, the rule-based fallback is used automatically.

## Running in Docker

```bash
docker build -t onboarding-assistant .
docker run --env-file .env -p 8000:8000 onboarding-assistant
```

See `Dockerfile` at the repo root for details.  The `ai/` module is built
into the same image as `backend/` — they are not separate services.

## Running tests

```bash
python -m pytest ai/tests/
# or, without pytest installed:
python ai/tests/test_generator.py
```

All tests run fully offline — no API key is needed.

## Design decisions worth noting

- **Diagram is never LLM-generated.** `diagram.py` only draws nodes/edges it
  has direct evidence for. This avoids hallucinated architecture connections.
- **Every output field traces back to input data or an explicit "unavailable"
  note.** The prompt forces this; the fallback path enforces it mechanically.
- **Fallback path exists so the team is never blocked by API access during
  the demo.**
- **Pre-send sanitization** (`sanitize.py`) redacts API keys, tokens, PEM
  headers, .env-style assignments, and known secret-bearing filenames before
  any data is sent to Anthropic.
- **Cost budget cap** (`AI_MAX_REQUESTS` env var) short-circuits to the
  fallback after N LLM calls, preventing runaway spend from traffic spikes.
- **Sustained 100% fallback rate** triggers a `WARNING` log event
  (`ai.fallback_alert`) — wire this to an alert in production.
- **Prompt injection** is mitigated by `<repo_analysis>` XML delimiters,
  an explicit security instruction in the system prompt, and Anthropic
  tool-use (structural output enforcement).
- **Model drift** — when the pinned model in `llm_client._MODEL` is bumped,
  re-validate grounding behaviour with `scripts/check_llm_output.py`.
  See the `MODEL DRIFT NOTE` comment in `prompts.py`.

## Running the grounding audit script

```bash
# With a real API key (validates live LLM output):
export ANTHROPIC_API_KEY=sk-ant-...
echo '{"project_name":"my-app","languages":["Python"],"frameworks":["FastAPI"],"dependencies":[{"name":"fastapi"}]}' \
  | python scripts/check_llm_output.py -

# Without an API key (validates fallback output):
python scripts/check_llm_output.py sample_analysis.json --no-llm
```

Exit code 0 = no grounding failures. Exit code 1 = hallucinated names detected.
