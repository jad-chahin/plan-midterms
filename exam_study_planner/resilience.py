from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def is_retryable_error(exc: Exception) -> bool:
    text = str(exc).lower()
    retry_markers = [
        "429",
        "rate limit",
        "temporarily unavailable",
        "timeout",
        "timed out",
        "connection reset",
        "service unavailable",
        "internal error",
        "resource exhausted",
    ]
    return any(marker in text for marker in retry_markers)


def retry_with_backoff(
    func: Callable[[], T],
    *,
    max_retries: int,
    base_seconds: float,
    max_sleep_seconds: float = 20.0,
) -> T:
    attempt = 0
    while True:
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            attempt += 1
            if attempt >= max_retries or not is_retryable_error(exc):
                raise
            sleep_s = min(max_sleep_seconds, base_seconds * (2 ** (attempt - 1)))
            # Small jitter to reduce thundering herd behavior on retries.
            time.sleep(sleep_s + random.uniform(0.0, 0.2))
