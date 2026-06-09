from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from koan.memory._retry import (
    _is_rate_limit,
    _retry_delay_hint,
    with_rate_limit_retry,
)


# ---------------------------------------------------------------------------
# _is_rate_limit
# ---------------------------------------------------------------------------

def test_is_rate_limit_detects_429_status_attribute() -> None:
    exc = ModelHTTPError(status_code=429, model_name="m", body={})
    assert _is_rate_limit(exc)


def test_is_rate_limit_ignores_400_empty_input() -> None:
    # Voyage's empty-input rejection is a 400, not a rate limit -- must not retry.
    exc = ModelHTTPError(
        status_code=400, model_name="m", body="Input cannot contain empty strings"
    )
    assert not _is_rate_limit(exc)


def test_is_rate_limit_detects_resource_exhausted_text() -> None:
    assert _is_rate_limit(RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"))


def test_is_rate_limit_false_for_plain_error() -> None:
    assert not _is_rate_limit(ValueError("something else"))


# ---------------------------------------------------------------------------
# _retry_delay_hint
# ---------------------------------------------------------------------------

def test_retry_delay_hint_parses_retry_in_message() -> None:
    assert _retry_delay_hint(RuntimeError("Please retry in 24.88s.")) == pytest.approx(24.88)


def test_retry_delay_hint_parses_retry_delay_field() -> None:
    assert _retry_delay_hint(RuntimeError("... 'retryDelay': '24s' ...")) == pytest.approx(24.0)


def test_retry_delay_hint_none_when_absent() -> None:
    assert _retry_delay_hint(RuntimeError("no delay here")) is None


# ---------------------------------------------------------------------------
# with_rate_limit_retry
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_retries_on_429_then_succeeds() -> None:
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ModelHTTPError(status_code=429, model_name="m", body={})
        return "ok"

    with patch("koan.memory._retry.asyncio.sleep", new=AsyncMock()) as slept:
        out = await with_rate_limit_retry(factory, attempts=3, label="t")

    assert out == "ok"
    assert calls["n"] == 3
    assert slept.await_count == 2


@pytest.mark.anyio
async def test_non_rate_limit_propagates_without_retry() -> None:
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        raise ValueError("nope")

    with patch("koan.memory._retry.asyncio.sleep", new=AsyncMock()) as slept:
        with pytest.raises(ValueError):
            await with_rate_limit_retry(factory, attempts=3, label="t")

    assert calls["n"] == 1
    slept.assert_not_awaited()


@pytest.mark.anyio
async def test_exhausts_attempts_and_reraises_last_error() -> None:
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        raise ModelHTTPError(status_code=429, model_name="m", body={})

    with patch("koan.memory._retry.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(ModelHTTPError):
            await with_rate_limit_retry(factory, attempts=2, label="t")

    assert calls["n"] == 2


@pytest.mark.anyio
async def test_honors_server_delay_hint_capped_at_max() -> None:
    async def factory() -> str:
        raise ModelHTTPError(
            status_code=429, model_name="m", body="Please retry in 100s."
        )

    with patch("koan.memory._retry.asyncio.sleep", new=AsyncMock()) as slept:
        with pytest.raises(ModelHTTPError):
            await with_rate_limit_retry(factory, attempts=2, max_delay=30.0, label="t")

    # 100s hint capped to the 30s ceiling.
    slept.assert_awaited_once_with(30.0)
