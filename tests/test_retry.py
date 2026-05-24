"""Tests for the shared retry_with_backoff helper.

Each test patches time.sleep to keep the suite hermetic and fast.
"""

from __future__ import annotations

import pytest

from calibre_toolkit import retry as retry_mod
from calibre_toolkit.retry import retry_with_backoff


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Skip actual waits — we only care that retry logic is correct."""
    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)


class TestSuccessPath:
    def test_returns_immediately_on_first_success(self):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        assert retry_with_backoff(fn, max_retries=3) == "ok"
        assert len(calls) == 1

    def test_retries_until_success(self):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("transient")
            return "ok"

        assert retry_with_backoff(fn, max_retries=3) == "ok"
        assert attempts["n"] == 3


class TestFailurePath:
    def test_raises_last_exception_after_exhausting_retries(self):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            raise RuntimeError(f"fail {attempts['n']}")

        with pytest.raises(RuntimeError, match="fail 3"):
            retry_with_backoff(fn, max_retries=3)
        assert attempts["n"] == 3

    def test_does_not_retry_non_listed_exception(self):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            raise ValueError("permanent")

        with pytest.raises(ValueError):
            retry_with_backoff(fn, max_retries=5, retry_on=(RuntimeError,))
        assert attempts["n"] == 1

    def test_max_retries_below_one_rejected(self):
        with pytest.raises(ValueError):
            retry_with_backoff(lambda: "ok", max_retries=0)


class TestRetryOnResult:
    def test_retries_when_predicate_says_so(self):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            return None if attempts["n"] < 3 else "ok"

        result = retry_with_backoff(
            fn,
            max_retries=5,
            should_retry_result=lambda r: r is None,
        )
        assert result == "ok"
        assert attempts["n"] == 3

    def test_returns_retry_worthy_result_when_exhausted(self):
        """If the predicate keeps saying retry but we run out, return the last value."""

        def fn():
            return None

        result = retry_with_backoff(
            fn,
            max_retries=3,
            should_retry_result=lambda r: r is None,
        )
        assert result is None


class TestBackoffSchedule:
    def test_sleep_called_with_exponential_delays(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(retry_mod.time, "sleep", lambda s: sleeps.append(s))

        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 4:
                raise RuntimeError("flaky")
            return "ok"

        retry_with_backoff(
            fn,
            max_retries=5,
            initial_delay=1.0,
            backoff_factor=2.0,
        )
        # Three failures → three sleeps before the fourth (winning) attempt.
        assert sleeps == [1.0, 2.0, 4.0]

    def test_no_sleep_after_final_attempt(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(retry_mod.time, "sleep", lambda s: sleeps.append(s))

        def fn():
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError):
            retry_with_backoff(fn, max_retries=3, initial_delay=0.1)
        # max_retries=3 → two sleeps (between attempts 1→2 and 2→3), none after attempt 3.
        assert len(sleeps) == 2
