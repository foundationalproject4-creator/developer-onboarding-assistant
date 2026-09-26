"""
Thin wrapper around the Anthropic API.

Isolated in its own module so:
- generator.py doesn't care which SDK/version is used
- it's trivial to mock in tests (see tests/test_generator.py)
- swapping models/providers later is a one-file change
"""

from __future__ import annotations

import os
from typing import Optional

_MODEL = "claude-sonnet-4-6"


class LLMUnavailableError(RuntimeError):
    """Raised when no API key is configured or the call fails."""


def call_llm(system_prompt: str, user_prompt: str) -> str:
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
    response = client.messages.create(
        model=_MODEL,
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text_parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "".join(text_parts)
