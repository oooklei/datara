"""Deterministic retry classification and backoff policy for worker failures."""

from __future__ import annotations

import re
from dataclasses import dataclass


_TRANSIENT = re.compile(r"timeout|timed? out|connection reset|temporar(?:y|ily)|econnreset|5\d\d", re.I)
_CONGESTION = re.compile(r"rate limit|too many|busy|queue full|throttl|overload", re.I)
_DETERMINISTIC = re.compile(r"syntax|validation|invalid|not found|unsupported|parse error", re.I)


def classify_error(exception_type: str | None, message: str | None, exit_code: int | None) -> str:
    """Classify a worker failure without relying on provider-specific exception classes."""
    text = " ".join(filter(None, (exception_type, message)))
    if exit_code in {2, 64, 65} or _DETERMINISTIC.search(text):
        return "deterministic"
    if _CONGESTION.search(text):
        return "congestion"
    if _TRANSIENT.search(text) or (exit_code is not None and exit_code >= 128):
        return "transient"
    return "external"


@dataclass(frozen=True)
class RetryDecision:
    strategy: str
    delay_seconds: int
    retryable: bool


def retry_decision(kind: str, failed_attempt: int, fallback_seconds: int) -> RetryDecision:
    """Return delay for the *next* attempt; transient retries are capped at 25s."""
    if kind == "deterministic":
        return RetryDecision(kind, 0, False)
    if kind == "transient":
        return RetryDecision(kind, min(25, 5 ** max(0, failed_attempt - 1)), True)
    if kind == "congestion":
        return RetryDecision(kind, max(30, fallback_seconds), True)
    return RetryDecision("external", max(1, fallback_seconds), True)
