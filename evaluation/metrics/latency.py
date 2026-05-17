"""Latency timing context manager.

    with latency_ms() as t:
        ... do work ...
    elapsed = t.elapsed_ms
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Stopwatch:
    elapsed_ms: int = 0


class latency_ms:
    """Context manager yielding a _Stopwatch with .elapsed_ms set on exit."""

    def __enter__(self) -> _Stopwatch:
        self._t0 = time.perf_counter_ns()
        self._sw = _Stopwatch()
        return self._sw

    def __exit__(self, exc_type, exc, tb) -> None:
        self._sw.elapsed_ms = (time.perf_counter_ns() - self._t0) // 1_000_000


__all__ = ["latency_ms"]
