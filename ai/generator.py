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
import threading
import time
from typing import Any, Dict, List, Optional, Union

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
            purpose=f.description or "Purpose not specified by analyzer.",
        )
    return ImportantFileExplanation(path=f, purpose="Purpose not specified by analyzer.")


def _dep_to_explanation(d: Union[str, DependencyEntry]) -> DependencyExplanation:
    name = d.name if isinstance(d, DependencyEntry) else d
    return DependencyExplanation(name=name, purpose="Purpose not specified by analyzer.")


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

def _fallback_generate(analysis: RepoAnalysis) -> OnboardingKnowledge:
    notes: List[str] = []

    if analysis.project_name:
        overview = (
            f"'{analysis.project_name}' is a project using "
            f"{', '.join(analysis.languages) or 'an unspecified language'}."
        )
    else:
        overview = "Project name was not provided by the repository analyzer."
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
        setup_guide=(
            ["Not derivable from the provided analysis data."]
            if not analysis.dependencies
            else [
                f"Install dependencies: {', '.join(_dep_name(d) for d in analysis.dependencies)}.",
                "Refer to the project README (if present) for environment-specific steps.",
            ]
        ),
        development_workflow=["Not derivable from the provided analysis data."],
        starter_tasks=(
            ["Explore the important files listed above to get oriented."]
            if important_files
            else ["No specific starter tasks could be generated — important files were not provided."]
        ),
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
