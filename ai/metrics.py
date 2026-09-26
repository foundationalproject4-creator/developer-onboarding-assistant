"""
Lightweight in-process metrics for the AI layer.

No external metrics library is required.  All counters and summaries are
written as structured log events AND accumulated in module-level state so
they can be queried programmatically in tests or health-check endpoints.

What is tracked
---------------
- Total requests, broken down by path (llm / fallback / error / cache_hit)
- Per-path call counts (llm_calls, fallback_calls, error_calls, cache_hits)
- Cumulative and per-bucket latency (ms)

Alerting guidance
-----------------
A SUSTAINED 100% fallback rate (i.e. llm_calls == 0 while fallback_calls > N)
almost always means:
  - ANTHROPIC_API_KEY is not set or has been rotated/expired.
  - The Anthropic service is down.
  - The model name in llm_client._MODEL is invalid.

In a real deployment this state should trigger a PagerDuty / OpsGenie alert.
A simple heuristic: if fallback_rate() > 0.95 AND total() > 10, page on-call.

Example Prometheus / Datadog integration
-----------------------------------------
Replace the AiMetrics class with one that increments actual metric objects:

    from prometheus_client import Counter, Histogram
    _llm_ok   = Counter("ai_llm_ok_total", "...")
    _fallback = Counter("ai_fallback_total", "...")
    _latency  = Histogram("ai_latency_seconds", "...", buckets=[0.1,0.5,1,2,5,10])

The calling code in router.py / generator.py does NOT change.
"""

from __future__ import annotations

import logging
import threading
from typing import List

log = logging.getLogger(__name__)

# How many consecutive fallbacks (no LLM success) before we emit a WARNING
# that should be wired to an alert in a real deployment.
_FALLBACK_ALERT_THRESHOLD = 10


class AiMetrics:
    """Thread-safe in-process counters and latency accumulator."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts = {"llm": 0, "fallback": 0, "error": 0, "cache_hit": 0}
        self._latencies_ms: List[float] = []
        self._consecutive_fallbacks = 0

    # ------------------------------------------------------------------
    # Write path (called from router.py and generator.py)
    # ------------------------------------------------------------------

    def record(self, path: str, latency_ms: float) -> None:
        """
        Record one completed request.

        ``path`` must be one of: ``"llm"``, ``"fallback"``, ``"error"``,
        ``"cache_hit"``.
        """
        with self._lock:
            self._counts[path] = self._counts.get(path, 0) + 1
            self._latencies_ms.append(latency_ms)

            if path == "llm" or path == "cache_hit":
                self._consecutive_fallbacks = 0
            elif path == "fallback":
                self._consecutive_fallbacks += 1

        self._emit_log(path, latency_ms)
        self._check_fallback_alert()

    # ------------------------------------------------------------------
    # Read path (health checks, tests)
    # ------------------------------------------------------------------

    def total(self) -> int:
        with self._lock:
            return sum(self._counts.values())

    def counts(self) -> dict:
        with self._lock:
            return dict(self._counts)

    def fallback_rate(self) -> float:
        """Fraction of requests that used the rule-based fallback (0.0–1.0)."""
        with self._lock:
            t = sum(self._counts.values())
            if t == 0:
                return 0.0
            return self._counts.get("fallback", 0) / t

    def avg_latency_ms(self) -> float:
        with self._lock:
            if not self._latencies_ms:
                return 0.0
            return sum(self._latencies_ms) / len(self._latencies_ms)

    def reset(self) -> None:
        """Reset all counters — used in tests."""
        with self._lock:
            self._counts = {"llm": 0, "fallback": 0, "error": 0, "cache_hit": 0}
            self._latencies_ms = []
            self._consecutive_fallbacks = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_log(self, path: str, latency_ms: float) -> None:
        with self._lock:
            snapshot = dict(self._counts)
            avg = (
                sum(self._latencies_ms) / len(self._latencies_ms)
                if self._latencies_ms else 0.0
            )
        log.info(
            "ai.metrics",
            extra={
                "json_fields": {
                    "event": "ai.metrics",
                    "path": path,
                    "latency_ms": round(latency_ms, 1),
                    "counts": snapshot,
                    "avg_latency_ms": round(avg, 1),
                }
            },
        )

    def _check_fallback_alert(self) -> None:
        with self._lock:
            consec = self._consecutive_fallbacks
        if consec >= _FALLBACK_ALERT_THRESHOLD:
            log.warning(
                # ALERT: wire this log line to PagerDuty / OpsGenie in production.
                # A sustained 100%% fallback rate means the LLM path is broken
                # (missing API key, expired credentials, or Anthropic outage).
                "ai.fallback_alert: %d consecutive requests used the fallback path. "
                "Check ANTHROPIC_API_KEY and Anthropic service status.",
                consec,
                extra={
                    "json_fields": {
                        "event": "ai.fallback_alert",
                        "consecutive_fallbacks": consec,
                        "alert": "SUSTAINED_FALLBACK — check ANTHROPIC_API_KEY and service status",
                    }
                },
            )


# Module-level singleton used by router.py and generator.py.
ai_metrics = AiMetrics()
