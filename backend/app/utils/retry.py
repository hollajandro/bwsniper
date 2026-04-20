"""
backend/app/utils/retry.py — Shared retry helper for transient network errors.
"""

import time

import requests


def with_retry(fn, max_attempts: int = 3, backoff: float = 2.0):
    """Call fn(), retrying on transient network errors with exponential backoff.

    Retryable exceptions: ConnectionError, Timeout, ChunkedEncodingError.
    Non-retryable exceptions (e.g. HTTPError for 4xx/5xx) propagate immediately.

    Args:
        fn:           Zero-argument callable to invoke.
        max_attempts: Maximum number of attempts (default 3).
        backoff:      Base backoff in seconds; doubles each retry (default 2.0).

    Returns:
        The return value of fn() on success.

    Raises:
        The last retryable exception if all attempts fail.
    """
    _RETRYABLE = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
    )
    last_exc: BaseException = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(backoff * (2 ** attempt))
    if last_exc is not None:
        raise last_exc
