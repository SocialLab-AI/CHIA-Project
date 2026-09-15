"""Software-owned timing verification and aggregation; never fills absent metrics with zero."""

import math
import statistics
from src.common.errors import MetricsError


def extract_generation_metrics(result):
    if (
        result.get("done") is not True
        or not isinstance(result.get("response"), str)
        or not result["response"].strip()
    ):
        raise MetricsError("Ollama did not return a completed nonempty generation.")
    names = (
        "total_duration",
        "load_duration",
        "prompt_eval_duration",
        "eval_duration",
        "prompt_eval_count",
        "eval_count",
    )
    for name in names:
        value = result.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise MetricsError(f"Ollama metric {name} is missing or invalid.")
    if (
        result["eval_duration"] <= 0
        or result["total_duration"] <= 0
        or result["eval_count"] <= 0
    ):
        raise MetricsError(
            "Ollama generation needs positive elapsed time and output tokens."
        )
    return {
        "total_latency_ms": result["total_duration"] / 1e6,
        "load_latency_ms": result["load_duration"] / 1e6,
        "prompt_eval_latency_ms": result["prompt_eval_duration"] / 1e6,
        "generation_latency_ms": result["eval_duration"] / 1e6,
        "prompt_tokens": result["prompt_eval_count"],
        "completion_tokens": result["eval_count"],
        "generation_tokens_per_second": result["eval_count"]
        / (result["eval_duration"] / 1e9),
    }


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
