# Bounded retry-with-backoff for transient LLM provider rate limits (HTTP 429).
#
# The mechanical memory paths (llm.generate, the reflect agent) call hosted
# models that emit 429 / RESOURCE_EXHAUSTED in bursts -- e.g. Gemini's free
# tier caps requests per minute. A short bounded retry rides out the transient
# window instead of failing the whole tool call. Non-rate-limit errors (a 400
# for malformed input, an auth failure) propagate immediately: retrying them
# only wastes time and quota.

from __future__ import annotations

import asyncio
import re
from typing import Awaitable, Callable, TypeVar

from ..logger import get_logger

log = get_logger("memory.retry")

T = TypeVar("T")

_DEFAULT_ATTEMPTS = 3
_MAX_DELAY_S = 30.0

# Provider-supplied delay hints, e.g. "Please retry in 24.88s." (Gemini message
# text) or "'retryDelay': '24s'" (RetryInfo detail). Either form is honored.
_RETRY_IN_RE = re.compile(r"retry in ([\d.]+)\s*s", re.IGNORECASE)
_RETRY_DELAY_RE = re.compile(r"retryDelay'?\s*:\s*'?([\d.]+)\s*s", re.IGNORECASE)


def _is_rate_limit(exc: BaseException) -> bool:
    """True if exc looks like a provider rate-limit / quota error (HTTP 429).

    Checks numeric status attributes first (pydantic-ai ModelHTTPError exposes
    .status_code; google-genai ClientError exposes .code), then falls back to
    the message text. A 400 (e.g. Voyage's empty-input rejection) is NOT a rate
    limit and must not be retried.
    """
    for attr in ("status_code", "code", "status"):
        if getattr(exc, attr, None) == 429:
            return True
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or "rate limit" in text.lower() or (
        "429" in text and "400" not in text
    )


def _retry_delay_hint(exc: BaseException) -> float | None:
    """Extract a server-suggested retry delay in seconds, if the error names one."""
    text = str(exc)
    for pattern in (_RETRY_IN_RE, _RETRY_DELAY_RE):
        m = pattern.search(text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


async def with_rate_limit_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = _DEFAULT_ATTEMPTS,
    max_delay: float = _MAX_DELAY_S,
    label: str = "llm call",
) -> T:
    """Run ``factory()``, retrying on transient 429 / rate-limit errors.

    ``factory`` is a zero-arg coroutine factory called once per attempt, so each
    retry gets a fresh awaitable. Backoff honors a server-provided retry delay
    when present (capped at ``max_delay``), otherwise exponential 1/2/4s.
    Non-rate-limit errors propagate immediately, and the final attempt's error
    is re-raised unchanged.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await factory()
        except Exception as exc:  # noqa: BLE001 - re-raised below when not retriable
            if attempt >= attempts or not _is_rate_limit(exc):
                raise
            hint = _retry_delay_hint(exc)
            delay = min(hint if hint is not None else 2.0 ** (attempt - 1), max_delay)
            log.warning(
                "%s hit rate limit (attempt %d/%d); retrying in %.1fs",
                label, attempt, attempts, delay,
            )
            await asyncio.sleep(delay)
    # Unreachable: the loop always returns or raises within `attempts` tries.
    raise RuntimeError("with_rate_limit_retry exhausted without returning")
