"""
Shared retry/backoff helper for external calls.

Before v1.2 the three external surfaces — Anthropic, fetch-ebook-metadata,
and the LC catalog — each handled (or failed to handle) transient errors
differently. The LC catalog in particular returned None on any failure
with no retry, so a 1–2 second outage silently demoted a row to AI-only
classification.

This module centralises the retry policy: exponential backoff with a
short initial delay, capped at `max_retries` attempts, with each retry
logged at DEBUG so post-hoc audit-log review can attribute slow batches
to network flakiness rather than guessing.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from .logging_config import get_logger

_log = get_logger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    should_retry_result: Callable[[T], bool] | None = None,
    description: str = "external call",
) -> T:
    """Run `fn()` with exponential backoff, returning its result.

    The retry loop stops at the first success and re-raises the final
    exception (or returns the final result) once `max_retries` attempts
    are exhausted.

    Parameters
    ----------
    max_retries
        Total number of attempts (not additional retries). `max_retries=3`
        means up to three calls total: one initial + two retries.
    initial_delay
        Seconds to wait before the second attempt. Doubles on each retry
        with `backoff_factor=2.0` (default), so the sequence is 0.5s, 1s,
        2s, ... by default.
    retry_on
        Exception classes that trigger a retry. Anything else propagates
        immediately so we don't loop on programming errors.
    should_retry_result
        Optional predicate on a successful (non-raising) result. Used by
        the LC catalog path where the HTTP helper swallows errors and
        returns None — we want to retry that None just like an exception.
    description
        Short label used in DEBUG log lines so the trail explains which
        external service was struggling.
    """
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    delay = initial_delay
    last_exc: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            result = fn()
        except retry_on as e:
            last_exc = e
            if attempt == max_retries:
                _log.debug(
                    "%s failed on final attempt %d/%d: %s",
                    description, attempt, max_retries, e,
                )
                raise
            _log.debug(
                "%s failed on attempt %d/%d (%s); retrying in %.2fs",
                description, attempt, max_retries, e, delay,
            )
            time.sleep(delay)
            delay *= backoff_factor
            continue

        if should_retry_result is not None and should_retry_result(result):
            if attempt == max_retries:
                _log.debug(
                    "%s returned retry-worthy result on final attempt %d/%d",
                    description, attempt, max_retries,
                )
                return result
            _log.debug(
                "%s returned retry-worthy result on attempt %d/%d; retrying in %.2fs",
                description, attempt, max_retries, delay,
            )
            time.sleep(delay)
            delay *= backoff_factor
            continue

        return result

    # Unreachable: the loop either returns or raises.
    assert last_exc is not None
    raise last_exc
