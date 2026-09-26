"""
Thin wrapper around the Anthropic API.

Isolated in its own module so:
- generator.py doesn't care which SDK/version is used
- it's trivial to mock in tests (see tests/test_generator.py)
- swapping models/providers later is a one-file change

Production improvements applied:
- Uses Anthropic tool-use (function calling) so the model returns structured
  output directly — no JSON-fence stripping or fragile text parsing.
- Retries up to MAX_RETRIES times with exponential back-off for transient
  errors (rate limits, timeouts, 5xx).  Auth / invalid-input errors fail fast.
- Enforces a hard timeout (REQUEST_TIMEOUT_SECONDS) so a hung request never
  blocks the endpoint indefinitely.
- Logs token usage after every successful call for cost visibility.
- Exposes an async variant (acall_llm) for use from async FastAPI endpoints.

Secret-leak policy
------------------
ANTHROPIC_API_KEY is read from the environment and passed directly to the SDK
client constructor.  It is NEVER logged, included in exception messages, or
returned in any data structure.  LLMUnavailableError messages reference only
the environment variable *name* (e.g. "ANTHROPIC_API_KEY is not set"), never
its value.

Provider abstraction seam
--------------------------
``call_llm`` and ``acall_llm`` are the only symbols that generator.py imports.
To add a second provider (e.g. OpenAI, Google Gemini, a local Ollama):

1. Implement a new module, e.g. ``ai/llm_openai.py``, exposing:
       call_llm(system_prompt, user_prompt) -> Dict[str, Any]
       acall_llm(system_prompt, user_prompt) -> Dict[str, Any]
   The tool schema in ``ONBOARDING_TOOL`` is provider-agnostic JSON Schema;
   adapt it to the target provider's function-calling format.

2. In generator.py replace:
       from .llm_client import LLMUnavailableError, acall_llm, call_llm
   with the new module import.  No other code changes are needed.

3. To support runtime provider selection (e.g. env var ``AI_PROVIDER``),
   add a thin dispatch layer:
       from .llm_dispatch import acall_llm, call_llm, LLMUnavailableError
   where llm_dispatch.py reads AI_PROVIDER and delegates.

The current implementation supports only Anthropic.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"

# Maximum wall-clock time for a single LLM API call (seconds).
REQUEST_TIMEOUT_SECONDS = 30

# How many total attempts to make before giving up on transient errors.
MAX_RETRIES = 3

# Base delay for exponential back-off (seconds).  Actual delay = BASE * 2^attempt.
_BACKOFF_BASE = 1.0

# ---------------------------------------------------------------------------
# Tool (function-calling) schema that describes the structured output format.
# The model MUST call this tool, giving us a strongly-typed dict back instead
# of free-form text we'd have to parse.
# ---------------------------------------------------------------------------

ONBOARDING_TOOL: Dict[str, Any] = {
    "name": "emit_onboarding_knowledge",
    "description": (
        "Emit structured onboarding knowledge derived from the repository analysis."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_overview": {"type": "string"},
            "tech_stack": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {"type": ["string", "null"]},
                        "role": {"type": "string"},
                    },
                    "required": ["name", "role"],
                },
            },
            "architecture": {"type": "string"},
            "important_files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "purpose": {"type": "string"},
                    },
                    "required": ["path", "purpose"],
                },
            },
            "dependencies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "purpose": {"type": "string"},
                    },
                    "required": ["name", "purpose"],
                },
            },
            "setup_guide": {"type": "array", "items": {"type": "string"}},
            "development_workflow": {"type": "array", "items": {"type": "string"}},
            "starter_tasks": {"type": "array", "items": {"type": "string"}},
            "data_completeness_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "project_overview",
            "tech_stack",
            "architecture",
            "important_files",
            "dependencies",
            "setup_guide",
            "development_workflow",
            "starter_tasks",
            "data_completeness_notes",
        ],
    },
}


class LLMUnavailableError(RuntimeError):
    """Raised when no API key is configured or the call fails."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_transient(exc: Exception) -> bool:
    """Return True for errors worth retrying (rate limits, timeouts, 5xx)."""
    try:
        import anthropic
    except ImportError:
        return False

    # Never retry auth / permission / invalid-input errors.
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return False
    # Retry rate-limit and API errors (which cover 5xx).
    if isinstance(exc, (anthropic.RateLimitError, anthropic.APIStatusError)):
        return True
    # Retry connection / timeout errors.
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return True
    return False


def _log_usage(response: Any) -> None:
    """Log token usage from a Messages API response."""
    try:
        usage = response.usage
        log.info(
            "LLM token usage — input: %d, output: %d, total: %d",
            usage.input_tokens,
            usage.output_tokens,
            usage.input_tokens + usage.output_tokens,
        )
    except Exception:  # pragma: no cover
        pass  # Best-effort; never let logging crash the call.


def _extract_tool_input(response: Any) -> Dict[str, Any]:
    """Pull the tool_use block's input dict out of a Messages response."""
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input  # type: ignore[return-value]
    raise LLMUnavailableError(
        "Model did not call the expected tool. Response content: "
        + repr(response.content)
    )


def _build_create_kwargs(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    return {
        "model": _MODEL,
        "max_tokens": 2000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "tools": [ONBOARDING_TOOL],
        "tool_choice": {"type": "tool", "name": ONBOARDING_TOOL["name"]},
        "timeout": REQUEST_TIMEOUT_SECONDS,
    }


# ---------------------------------------------------------------------------
# Synchronous client
# ---------------------------------------------------------------------------

def call_llm(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """
    Call the Anthropic API using tool-use and return the structured dict.

    Retries up to MAX_RETRIES times for transient errors with exponential
    back-off.  Fails fast on authentication / invalid-input errors.
    Raises LLMUnavailableError on final failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMUnavailableError("ANTHROPIC_API_KEY is not set")

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailableError(
            "The 'anthropic' package is not installed. Add it to requirements."
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = _build_create_kwargs(system_prompt, user_prompt)

    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(**kwargs)
            _log_usage(response)
            return _extract_tool_input(response)
        except Exception as exc:
            if not _is_transient(exc):
                raise LLMUnavailableError(f"Non-retryable LLM error: {exc}") from exc
            last_exc = exc
            delay = _BACKOFF_BASE * (2 ** attempt)
            log.warning(
                "Transient LLM error on attempt %d/%d (%s: %s); retrying in %.1fs",
                attempt + 1,
                MAX_RETRIES,
                type(exc).__name__,
                exc,
                delay,
            )
            time.sleep(delay)

    raise LLMUnavailableError(
        f"LLM call failed after {MAX_RETRIES} attempts. Last error: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# Async client (for use from async FastAPI endpoints)
# ---------------------------------------------------------------------------

async def acall_llm(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """
    Async variant of call_llm.  Uses the AsyncAnthropic client so FastAPI can
    handle concurrent requests without blocking the event loop.

    Retries and timeout behaviour are identical to the sync version.
    Raises LLMUnavailableError on final failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMUnavailableError("ANTHROPIC_API_KEY is not set")

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailableError(
            "The 'anthropic' package is not installed. Add it to requirements."
        ) from exc

    client = anthropic.AsyncAnthropic(api_key=api_key)
    kwargs = _build_create_kwargs(system_prompt, user_prompt)

    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.messages.create(**kwargs)
            _log_usage(response)
            return _extract_tool_input(response)
        except Exception as exc:
            if not _is_transient(exc):
                raise LLMUnavailableError(f"Non-retryable LLM error: {exc}") from exc
            last_exc = exc
            delay = _BACKOFF_BASE * (2 ** attempt)
            log.warning(
                "Transient LLM error on attempt %d/%d (%s: %s); retrying in %.1fs",
                attempt + 1,
                MAX_RETRIES,
                type(exc).__name__,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    raise LLMUnavailableError(
        f"LLM call failed after {MAX_RETRIES} attempts. Last error: {last_exc}"
    ) from last_exc
