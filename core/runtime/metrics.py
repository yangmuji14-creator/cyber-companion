"""Small in-process runtime metrics without conversation-content collection."""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass
from time import monotonic


@dataclass
class _Metric:
    count: int = 0
    failures: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cached_tokens: int = 0
    total_ttft_ms: float = 0.0
    max_ttft_ms: float = 0.0
    ttft_samples: int = 0


class RuntimeMetrics:
    """Aggregate bounded counters for health and latency diagnostics."""

    def __init__(self) -> None:
        self._started_at = monotonic()
        self._lock = threading.Lock()
        self._metrics: dict[str, _Metric] = defaultdict(_Metric)

    def record(
        self,
        name: str,
        duration_ms: float,
        *,
        success: bool = True,
        usage: dict[str, int] | None = None,
        first_token_ms: float | None = None,
    ) -> None:
        usage = usage or {}
        with self._lock:
            metric = self._metrics[name]
            metric.count += 1
            metric.failures += int(not success)
            metric.total_ms += max(0.0, duration_ms)
            metric.max_ms = max(metric.max_ms, duration_ms)
            metric.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
            metric.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
            metric.cache_creation_input_tokens += int(
                usage.get("cache_creation_input_tokens", 0) or 0
            )
            metric.cache_read_input_tokens += int(
                usage.get("cache_read_input_tokens", 0) or 0
            )
            metric.cached_tokens += int(usage.get("cached_tokens", 0) or 0)
            if first_token_ms is not None and first_token_ms >= 0:
                metric.total_ttft_ms += first_token_ms
                metric.max_ttft_ms = max(metric.max_ttft_ms, first_token_ms)
                metric.ttft_samples += 1

    def snapshot(self) -> dict:
        with self._lock:
            operations = {}
            for name, metric in sorted(self._metrics.items()):
                if not metric.count:
                    continue
                item = {
                    "count": metric.count,
                    "failures": metric.failures,
                    "avg_ms": round(metric.total_ms / metric.count, 1),
                    "max_ms": round(metric.max_ms, 1),
                    "prompt_tokens": metric.prompt_tokens,
                    "completion_tokens": metric.completion_tokens,
                    "total_tokens": metric.prompt_tokens + metric.completion_tokens,
                }
                if (
                    metric.cache_creation_input_tokens
                    or metric.cache_read_input_tokens
                    or metric.cached_tokens
                    or metric.ttft_samples
                ):
                    item.update({
                        "cache_creation_input_tokens": metric.cache_creation_input_tokens,
                        "cache_read_input_tokens": metric.cache_read_input_tokens,
                        "cached_tokens": metric.cached_tokens,
                        "cache_hit_ratio": round(
                            (metric.cached_tokens or metric.cache_read_input_tokens)
                            / max(1, metric.prompt_tokens), 4,
                        ),
                        "ttft_samples": metric.ttft_samples,
                        "avg_ttft_ms": round(
                            metric.total_ttft_ms / metric.ttft_samples, 1
                        ) if metric.ttft_samples else None,
                        "max_ttft_ms": round(metric.max_ttft_ms, 1),
                    })
                operations[name] = item
        return {
            "uptime_seconds": round(monotonic() - self._started_at, 1),
            "operations": operations,
        }

    def reset(self) -> None:
        with self._lock:
            self._started_at = monotonic()
            self._metrics.clear()


runtime_metrics = RuntimeMetrics()
