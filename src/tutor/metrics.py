"""Software-owned timing verification and aggregation; never fills absent metrics with zero."""

import math
import statistics
from src.common.errors import MetricsError


def summarize_performance(samples):
    if not samples:
        raise MetricsError("Cannot aggregate empty software samples.")
    values = [s["wall_latency_ms"] for s in samples]
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise MetricsError("Software wall times must be finite and positive.")
    return {
        "latency_ms": statistics.median(values),
        "mean_latency_ms": statistics.mean(values),
        "p95_latency_ms": sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)],
        "throughput_qps": len(values) / (sum(values) / 1000),
        "sample_count": len(values),
        "answer_quality": None,
        "quality_method": "not_evaluated_smoke_profile",
    }
