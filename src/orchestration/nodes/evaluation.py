"""Evaluation-owned verification node; keeps native latency distinct from simulation time."""

import math
from src.common.errors import MetricsError
from src.common.logging import invoke


def verify_results(config, candidate_id, software, hardware):
    for name, result in (("software", software), ("hardware", hardware)):
        if (
            not isinstance(result, dict)
            or result.get("status") != "completed"
            or result.get("candidate_id") != candidate_id
        ):
            raise MetricsError(
                f"{name} result does not belong to this completed candidate."
            )
        if result.get(name) != config[name]:
            raise MetricsError(f"{name} executed knobs differ from the candidate.")
        if not result.get("provenance"):
            raise MetricsError(f"{name} runtime provenance is absent.")

    def positive(value):
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and value > 0
        )

    sw = software["metrics"]
    hw = hardware["metrics"]
    for value in (
        sw.get("latency_ms"),
        sw.get("throughput_qps"),
        hw.get("simulated_seconds"),
        hw.get("sim_ticks"),
        hw.get("instructions"),
    ):
        if not positive(value):
            raise MetricsError("Primary metric is missing, non-finite or nonpositive.")
    quality = sw.get("answer_quality")
    question_count = sw.get("question_count")
    if (
        isinstance(quality, bool)
        or not isinstance(quality, (int, float))
        or not math.isfinite(quality)
        or not 0 <= quality <= 1
        or type(question_count) is not int
        or question_count < 1
    ):
        raise MetricsError("Tutor quality evidence is missing or invalid.")
    expected_samples = question_count * config["measurement"]["software_repetitions"]
    if sw.get("sample_count") != expected_samples:
        raise MetricsError("Software sample count differs from requested repetitions.")
    dataset = software.get("dataset", {})
    if (
        not dataset.get("dataset_id")
        or dataset.get("reference_visible_to_model") is not False
        or dataset.get("license") != "CC BY 4.0"
    ):
        raise MetricsError("Tutor dataset provenance or reference isolation is absent.")
    if hardware.get("correctness", {}).get("status") != "PASS" or not hardware[
        "provenance"
    ].get("resolved_config_verified"):
        raise MetricsError(
            "Hardware correctness or resolved-config evidence is absent."
        )
    for name in ("max_absolute_error", "mean_squared_error"):
        value = hardware["correctness"].get(name)
        limit = hardware["provenance"].get("correctness_tolerance", {}).get(name)
        if (
            isinstance(value, bool)
            or isinstance(limit, bool)
            or not isinstance(value, (int, float))
            or not isinstance(limit, (int, float))
            or not math.isfinite(value)
            or not math.isfinite(limit)
            or value < 0
            or limit < 0
            or value > limit
        ):
            raise MetricsError(
                "Hardware numerical acceptance evidence is missing or invalid."
            )
    for field in ("cycles_per_core", "ipc_per_core", "l1d_miss_rate_per_core"):
        values = hw.get(field, [])
        if len(values) != config["hardware"]["cores"] or any(
            not isinstance(v, (int, float))
            or isinstance(v, bool)
            or not math.isfinite(v)
            or v < 0
            for v in values
        ):
            raise MetricsError("Incomplete per-core metrics.")
    for value in hw["l1d_miss_rate_per_core"] + [hw.get("l2_miss_rate", -1)]:
        if (
            not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            raise MetricsError("Cache miss rates must be fractions in [0,1].")
    return {
        "feasible": True,
        "objectives": {
            "native_latency_ms": sw["latency_ms"],
            "proxy_simulated_seconds": hw["simulated_seconds"],
            "answer_quality_loss": 1.0 - quality,
        },
        "answer_quality": quality,
        "quality_evaluated": True,
        "scope": "qwen_mixed_qa_quality_plus_attention_proxy",
        "comparison_group": {
            "context_tokens": config["workload"]["context_tokens"],
            "profile": config["profile"],
            "dataset_id": dataset["dataset_id"],
            "question_count": question_count,
        },
    }


def evaluation_node(mapped, software, hardware, context):
    def evaluate():
        if (
            mapped["event"]["status"] != "completed"
            or software["event"]["status"] != "completed"
            or hardware["event"]["status"] != "completed"
        ):
            raise MetricsError("A required upstream node did not complete.")
        return verify_results(
            mapped["value"]["candidate"],
            context["candidate_id"],
            software["value"],
            hardware["value"],
        )

    return invoke("evaluation", context, evaluate)
