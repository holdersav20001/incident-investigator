"""In-memory metrics registry — counters and histograms.

No external dependencies (no Prometheus client library required for V1).
The registry can be serialised to a dict snapshot and served via the API,
or replaced with a real Prometheus client in V2 by implementing the same
Counter / Histogram interface.

Thread-safety: all mutations use a module-level threading.Lock per object.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

# Sentinel for the "no labels" label-set
_NO_LABELS: tuple[()] = ()


def _labels_key(labels: dict[str, str] | None) -> tuple:
    if not labels:
        return _NO_LABELS
    return tuple(sorted(labels.items()))


class Counter:
    """Monotonically increasing counter, optionally with label dimensions."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._values: dict[tuple, int] = defaultdict(int)

    def inc(self, amount: int = 1, *, labels: dict[str, str] | None = None) -> None:
        key = _labels_key(labels)
        with self._lock:
            self._values[key] += amount

    def value(self, *, labels: dict[str, str] | None = None) -> int:
        return self._values[_labels_key(labels)]

    def snapshot(self) -> dict[tuple, dict[str, Any]]:
        with self._lock:
            return {k: {"value": v} for k, v in self._values.items()}


class Histogram:
    """Records a series of float observations and computes basic statistics."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._values: list[float] = []

    def observe(self, value: float) -> None:
        with self._lock:
            self._values.append(value)

    def count(self) -> int:
        return len(self._values)

    def mean(self) -> float:
        if not self._values:
            return 0.0
        return sum(self._values) / len(self._values)

    def percentile(self, p: float) -> float:
        """Return the p-th percentile (0–100) of observed values."""
        if not self._values:
            return 0.0
        sorted_vals = sorted(self._values)
        idx = int(len(sorted_vals) * p / 100)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "count": self.count(),
                "mean": round(self.mean(), 3),
                "p50": round(self.percentile(50), 3),
                "p95": round(self.percentile(95), 3),
                "p99": round(self.percentile(99), 3),
            }


class MetricsRegistry:
    """Central registry for all in-process metrics.

    Use `counter(name)` / `histogram(name)` to get-or-create metrics.
    Use `snapshot()` to read a point-in-time copy of all values.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}

    def counter(self, name: str) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name)
            return self._counters[name]

    def histogram(self, name: str) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name)
            return self._histograms[name]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": {name: c.snapshot() for name, c in self._counters.items()},
                "histograms": {name: h.snapshot() for name, h in self._histograms.items()},
            }
