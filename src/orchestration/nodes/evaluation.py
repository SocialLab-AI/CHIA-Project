"""Evaluation-owned verification node; keeps native latency distinct from simulation time."""

import math
import re
from src.common.errors import MetricsError
from src.common.logging import invoke
from src.hardware.energy_mapping import ENERGY_SCOPE


REQUIRED_ENERGY_COMPONENTS = {
    "cpu0_l1i",
    "cpu0_l1d",
    "cpu1_l1i",
    "cpu1_l1d",
    "shared_l2",
}


def verify_results(config, candidate_id, software, hardware, energy=None):
    energy = energy or (
        hardware.get("energy_evidence") if isinstance(hardware, dict) else None
    )
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

    hardware_stats_sha256 = hardware.get("provenance", {}).get("stats_sha256")
    if (
        not isinstance(energy, dict)
        or energy.get("status") != "completed"
        or energy.get("candidate_id") != candidate_id
        or energy.get("hardware_result_id")
        != hardware.get("provenance", {}).get("gem5_result_sha256")
        or not isinstance(hardware_stats_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", hardware_stats_sha256)
        or energy.get("stats_sha256") != hardware_stats_sha256
        or not energy.get("provenance")
    ):
        raise MetricsError("Energy result is stale or belongs to another hardware run.")

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
    energy_uj = energy.get("metrics", {}).get("estimated_cache_dynamic_energy_uj")
    if not positive(energy_uj):
        raise MetricsError("Energy estimate is missing, nonfinite or nonpositive.")
    if (
        hw.get("energy_uj") != energy_uj
        or hw.get("estimated_cache_dynamic_energy_uj") != energy_uj
        or hw.get("energy_scope") != energy.get("scope")
        or energy.get("scope") != ENERGY_SCOPE
    ):
        raise MetricsError("Hardware result does not preserve verified energy evidence.")
    component_names = {
        component.get("name", "").split(".")[-1]
        for component in energy.get("components", [])
        if isinstance(component, dict)
    }
    if (
        len(energy.get("components", [])) != 5
        or component_names != REQUIRED_ENERGY_COMPONENTS
    ):
        raise MetricsError("Energy result lacks the five verified cache components.")
    provenance = energy["provenance"]
    for field in (
        "container_image_digest",
        "accelergy_version",
        "accelergy_commit",
        "mcpat_version",
        "mcpat_commit",
        "plugin_commit",
        "mapping_sha256",
        "architecture_sha256",
        "action_counts_sha256",
        "energy_result_sha256",
    ):
        if not isinstance(provenance.get(field), str) or not provenance[field]:
            raise MetricsError(f"Energy provenance is missing {field}.")
    for field in (
        "mapping_sha256",
        "architecture_sha256",
        "action_counts_sha256",
        "energy_result_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", provenance[field]):
            raise MetricsError(f"Energy provenance has an invalid {field}.")
    duration = provenance.get("execution_duration_seconds")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration < 0
        or provenance.get("energy_scope") != ENERGY_SCOPE
    ):
        raise MetricsError("Energy execution provenance is missing or invalid.")
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
        dataset.get("dataset_id") != "openstax-college-physics-2e-ch4-concepts-v1"
        or dataset.get("source_url") != "https://openstax.org/books/college-physics-2e/pages/4-conceptual-questions"
        or dataset.get("reference_visible_to_model") is not False
        or dataset.get("license") != "CC BY-NC-SA 4.0"
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
            "estimated_cache_dynamic_energy_uj": energy_uj,
            "answer_quality_loss": 1.0 - quality,
        },
        "answer_quality": quality,
        "quality_evaluated": True,
        "scope": "openstax_quality_plus_qwen_attention_proxy_plus_cache_dynamic_energy",
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
            hardware["value"].get("energy_evidence"),
        )

    return invoke("evaluation", context, evaluate)
