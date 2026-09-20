#!/usr/bin/env python3
"""Run a repeated, fair gem5 comparison of original and Qwen-shaped proxies."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics
import time
import uuid

import yaml

from scripts.run_proxy_fidelity import _run_hardware_cases
from src.common.candidate import Candidate, ROOT, baseline_candidate
from src.common.errors import ConfigError, MetricsError
from src.common.records import atomic_json
from src.common.security import safe_id, within
from src.hardware.proxy_fidelity import analyze_fidelity, render_trend_svg


PROFILES = {
    "original-corrected": {
        "query_heads": 4,
        "kv_heads": 2,
        "head_dimension": 32,
        "layers": 1,
    },
    "qwen-shaped": {
        "query_heads": 14,
        "kv_heads": 2,
        "head_dimension": 64,
        "layers": 1,
    },
}

NUMERICAL_FIELDS = (
    "max_absolute_error",
    "mean_squared_error",
    "root_mean_squared_error",
    "reference_rms",
    "reference_max_absolute",
    "normalized_rmse",
    "normalized_max_error",
)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"Cannot read comparison evidence file {path.name}.") from error
    if not isinstance(value, dict):
        raise ConfigError(f"Comparison evidence file {path.name} must be an object.")
    return value


def load_config(path) -> dict:
    """Validate a strict operator configuration without contacting the cluster."""

    source = Path(path).resolve()
    value = yaml.safe_load(source.read_text(encoding="utf-8"))
    required = {
        "experiment_id",
        "contexts",
        "trials_per_context",
        "results_root",
        "native_evidence_directory",
        "hardware",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ConfigError("Proxy-comparison configuration fields are incomplete or unknown.")
    value["experiment_id"] = safe_id(value["experiment_id"])
    if value["contexts"] != [128, 256, 512, 1024, 2048]:
        raise ConfigError("Proxy comparison requires contexts 128 through 2048.")
    if type(value["trials_per_context"]) is not int or not (
        2 <= value["trials_per_context"] <= 5
    ):
        raise ConfigError("trials_per_context must be between two and five.")
    for field in ("results_root", "native_evidence_directory"):
        candidate = Path(value[field])
        if candidate.is_absolute():
            raise ConfigError(f"{field} must be repository-relative.")
        value[field] = str(within(ROOT, candidate))
    evidence = Path(value["native_evidence_directory"])
    for filename in ("model-profile.json", "native-context-sweep.json"):
        if not (evidence / filename).is_file():
            raise ConfigError(f"native_evidence_directory is missing {filename}.")

    hardware = value["hardware"]
    hardware_required = {
        "mode",
        "ray_address",
        "image",
        "timeout_seconds",
        "correctness_tolerance",
    }
    if not isinstance(hardware, dict) or set(hardware) != hardware_required:
        raise ConfigError("Proxy-comparison hardware settings are incomplete or unknown.")
    if hardware["mode"] not in {"local", "chia"}:
        raise ConfigError("hardware.mode must be local or chia.")
    if not isinstance(hardware["ray_address"], str) or not hardware["ray_address"]:
        raise ConfigError("hardware.ray_address must be nonempty text.")
    if not isinstance(hardware["image"], str) or not hardware["image"]:
        raise ConfigError("hardware.image must be nonempty text.")
    if type(hardware["timeout_seconds"]) is not int or hardware["timeout_seconds"] < 1:
        raise ConfigError("hardware.timeout_seconds must be a positive integer.")
    tolerance = hardware["correctness_tolerance"]
    if not isinstance(tolerance, dict) or set(tolerance) != {
        "max_absolute_error",
        "mean_squared_error",
    }:
        raise ConfigError("Hardware correctness tolerance is incomplete.")
    for name, number in tolerance.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)) or number < 0:
            raise ConfigError(f"hardware.correctness_tolerance.{name} is invalid.")
    return value


def _proxy_profile(shape: dict, maximum_context: int) -> dict:
    return {
        **shape,
        "maximum_tested_context": maximum_context,
        "kv_quantization": "Q4",
        "weight_quantization": None,
        "hidden_size": None,
        "feed_forward_dimension": None,
        "includes": [
            "one query vector per query head",
            "grouped-query KV-head mapping",
            "packed-Q4 KV-cache dequantization",
            "one representative attention layer",
            "two-thread execution",
        ],
        "excludes": [
            "Q/K/V projections",
            "MLP blocks",
            "all-layer repetition",
            "tokenization and sampling",
            "complete llama.cpp runtime behavior",
        ],
    }


def _native_kv_types(native: dict) -> dict:
    pairs = {
        (
            item.get("benchmark_provenance", {}).get("type_k"),
            item.get("benchmark_provenance", {}).get("type_v"),
        )
        for item in native.get("contexts", [])
    }
    if len(pairs) != 1 or None in next(iter(pairs), (None, None)):
        raise MetricsError("Native evidence does not report one consistent KV-cache type.")
    key_type, value_type = next(iter(pairs))
    return {"key": key_type, "value": value_type}


def load_native_evidence(config: dict) -> tuple[dict, dict]:
    """Load and cross-check the model profile and native context sweep."""

    evidence = Path(config["native_evidence_directory"])
    model = _read_json(evidence / "model-profile.json")
    native = _read_json(evidence / "native-context-sweep.json")
    if [item.get("context_tokens") for item in native.get("contexts", [])] != config[
        "contexts"
    ]:
        raise MetricsError("Native context evidence differs from the comparison protocol.")
    if native.get("model_sha256") != model.get("model_sha256"):
        raise MetricsError("Native sweep and model profile identify different GGUF files.")
    return model, native


def build_cases(config: dict) -> list[tuple[str, dict, str, int, int]]:
    """Interleave profiles deterministically to avoid profile-order bias."""

    timestamp = int(time.time())
    cases = []
    for trial in range(1, config["trials_per_context"] + 1):
        for context_tokens in config["contexts"]:
            for profile_id, shape in PROFILES.items():
                candidate = copy.deepcopy(baseline_candidate())
                candidate["workload"].update(shape)
                candidate["workload"]["context_tokens"] = context_tokens
                candidate["measurement"]["kernel_iterations"] = 1
                candidate = Candidate.from_dict(candidate, calibration=True).config
                run_id = safe_id(
                    f"proxycmp-{profile_id}-{context_tokens}-t{trial}-"
                    f"{timestamp}-{uuid.uuid4().hex[:8]}"
                )
                cases.append((run_id, candidate, profile_id, context_tokens, trial))
    return cases


def aggregate_trials(samples: list[dict], tolerance: dict) -> dict:
    """Aggregate repeated deterministic simulation results without hiding outliers."""

    if len(samples) < 2:
        raise MetricsError("At least two proxy-comparison trials are required.")
    seconds = [float(item["metrics"]["simulated_seconds"]) for item in samples]
    correctness = {
        name: max(float(item["correctness"][name]) for item in samples)
        for name in NUMERICAL_FIELDS
    }
    within = all(
        item["correctness"]["max_absolute_error"]
        <= tolerance["max_absolute_error"]
        and item["correctness"]["mean_squared_error"]
        <= tolerance["mean_squared_error"]
        for item in samples
    )
    return {
        "trial_count": len(samples),
        "simulated_seconds_samples": seconds,
        "metrics": {
            "simulated_seconds": statistics.mean(seconds),
            "simulated_seconds_median": statistics.median(seconds),
            "simulated_seconds_stddev": statistics.pstdev(seconds),
            "instructions_mean": statistics.mean(
                float(item["metrics"]["instructions"]) for item in samples
            ),
            "aggregate_ipc_mean": statistics.mean(
                float(item["metrics"]["aggregate_ipc"]) for item in samples
            ),
            "l2_miss_rate_mean": statistics.mean(
                float(item["metrics"]["l2_miss_rate"]) for item in samples
            ),
        },
        "correctness": correctness,
        "correctness_within_reviewed_tolerance": within,
        "trials": samples,
    }


def _trend_mape(native_normalized: list[float], proxy_normalized: list[float]) -> float:
    return statistics.mean(
        abs(proxy - native) / native
        for native, proxy in zip(native_normalized, proxy_normalized)
    ) * 100.0


def run_comparison(config: dict) -> dict:
    model, native = load_native_evidence(config)
    native_kv_types = _native_kv_types(native)
    model = {**model, "kv_cache_quantization": native_kv_types}

    hardware = config["hardware"]
    runtime = {
        "image": hardware["image"],
        "timeout_seconds": hardware["timeout_seconds"],
        "retries": 0,
        "correctness_tolerance": hardware["correctness_tolerance"],
        "enforce_correctness_tolerance": False,
        "calibration_mode": True,
    }
    directory = Path(config["results_root"]) / config["experiment_id"]
    directory.mkdir(parents=True, exist_ok=True)
    protocol = {
        "profiles": PROFILES,
        "contexts": config["contexts"],
        "trials_per_context": config["trials_per_context"],
        "image": hardware["image"],
        "correctness_tolerance": hardware["correctness_tolerance"],
        "kernel_sha256": hashlib.sha256(
            (ROOT / "gem5/attention_kv.c").read_bytes()
        ).hexdigest(),
    }
    protocol_id = hashlib.sha256(
        json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    checkpoint_path = directory / "checkpoint.json"
    if checkpoint_path.is_file():
        checkpoint = _read_json(checkpoint_path)
        if checkpoint.get("protocol_id") != protocol_id:
            raise ConfigError(
                "Existing checkpoint belongs to a different comparison protocol."
            )
        completed = checkpoint.get("completed", {})
        if not isinstance(completed, dict):
            raise ConfigError("Comparison checkpoint is malformed.")
    else:
        completed = {}

    cases = build_cases(config)
    grouped = {
        profile_id: {context: [] for context in config["contexts"]}
        for profile_id in PROFILES
    }
    for index, case in enumerate(cases, start=1):
        run_id, candidate, profile_id, context_tokens, trial = case
        key = f"{profile_id}|{context_tokens}|{trial}"
        expected_id = Candidate.from_dict(candidate, calibration=True).candidate_id
        if key in completed:
            sample = completed[key]
            if sample.get("candidate_id") != expected_id:
                raise ConfigError("Checkpoint candidate differs from the current protocol.")
            print(f"[comparison {index}/{len(cases)}] {key} resumed", flush=True)
        else:
            result = _run_hardware_cases(
                [(run_id, candidate)],
                runtime,
                hardware["mode"],
                hardware["ray_address"],
            )[0]
            sample = {
                "run_id": run_id,
                "trial": trial,
                "candidate_id": result["candidate_id"],
                "metrics": result["metrics"],
                "correctness": result["correctness"],
                "provenance": result["provenance"],
                "artifacts": result["artifacts"],
            }
            completed[key] = sample
            atomic_json(
                checkpoint_path,
                {
                    "schema_version": "0.1.0",
                    "experiment_id": config["experiment_id"],
                    "protocol_id": protocol_id,
                    "protocol": protocol,
                    "completed": completed,
                },
            )
        grouped[profile_id][context_tokens].append(sample)

    profiles = {}
    for profile_id, shape in PROFILES.items():
        contexts = []
        for context_tokens in config["contexts"]:
            aggregate = aggregate_trials(
                grouped[profile_id][context_tokens],
                hardware["correctness_tolerance"],
            )
            contexts.append({"context_tokens": context_tokens, **aggregate})
        hardware_evidence = {
            "contexts": contexts,
            "sensitivity": [],
            "reviewed_correctness_tolerance": hardware["correctness_tolerance"],
            "measurement_scope": (
                "whole gem5 proxy program including setup and FP32 reference"
            ),
        }
        proxy = _proxy_profile(shape, max(config["contexts"]))
        analysis = analyze_fidelity(model, native, hardware_evidence, proxy=proxy)
        analysis["normalized_trend_mape_percent"] = _trend_mape(
            analysis["native_normalized_latency"],
            analysis["proxy_normalized_latency"],
        )
        profiles[profile_id] = {
            "shape": shape,
            "kernel_iterations": 1,
            "contexts": contexts,
            "analysis": analysis,
        }

    return {
        "schema_version": "0.1.0",
        "kind": "proxy_profile_comparison",
        "experiment_id": config["experiment_id"],
        "native_model_sha256": model["model_sha256"],
        "protocol_id": protocol_id,
        "native_kv_cache_types": native_kv_types,
        "proxy_kv_cache_type": "Q4",
        "trials_per_context": config["trials_per_context"],
        "contexts": config["contexts"],
        "profiles": profiles,
        "claim_boundary": (
            "This compares one-layer attention proxies. It does not simulate complete Qwen."
        ),
    }


def render_report(result: dict) -> str:
    lines = [
        "# Original versus Qwen-shaped proxy comparison",
        "",
        f"Native KV cache: `{result['native_kv_cache_types']}`. Proxy KV cache: `Q4`.",
        "",
        "The KV representations differ. Timing trends and numerical approximation are "
        "reported separately; this experiment does not claim full-model equivalence.",
        "",
        "## Summary",
        "",
        "| Profile | Shape Q/KV/D | Spearman rho | Trend MAPE | Tolerance violations |",
        "|---|---:|---:|---:|---|",
    ]
    for profile_id, profile in result["profiles"].items():
        shape = profile["shape"]
        analysis = profile["analysis"]
        violations = analysis["context_tolerance_violations"]
        lines.append(
            f"| {profile_id} | {shape['query_heads']}/{shape['kv_heads']}/"
            f"{shape['head_dimension']} | {analysis['context_spearman_rho']:.4f} | "
            f"{analysis['normalized_trend_mape_percent']:.3f}% | "
            f"{', '.join(map(str, violations)) or 'none'} |"
        )
    for profile_id, profile in result["profiles"].items():
        lines += [
            "",
            f"## {profile_id}",
            "",
            "| Context | Mean gem5 seconds | Stddev | Worst normalized RMSE | "
            "Worst normalized max error |",
            "|---:|---:|---:|---:|---:|",
        ]
        for item in profile["contexts"]:
            lines.append(
                f"| {item['context_tokens']} | "
                f"{item['metrics']['simulated_seconds']:.9f} | "
                f"{item['metrics']['simulated_seconds_stddev']:.9f} | "
                f"{item['correctness']['normalized_rmse']:.9f} | "
                f"{item['correctness']['normalized_max_error']:.9f} |"
            )
    lines += [
        "",
        "## Decision rule",
        "",
        "Prefer the Qwen-shaped profile only if it remains numerically controlled and its "
        "normalized context trend is at least as defensible as the corrected original. "
        "Do not choose a profile from absolute gem5 time alone because the modeled work differs.",
        "",
        result["claim_boundary"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the protocol and native evidence without submitting jobs.",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    if args.validate_only:
        model, native = load_native_evidence(config)
        print(
            json.dumps(
                {
                    "experiment_id": config["experiment_id"],
                    "contexts": config["contexts"],
                    "trials_per_context": config["trials_per_context"],
                    "planned_hardware_jobs": (
                        len(PROFILES)
                        * len(config["contexts"])
                        * config["trials_per_context"]
                    ),
                    "native_model_sha256": model["model_sha256"],
                    "native_kv_cache_types": _native_kv_types(native),
                    "validation": "passed",
                    "execution": "not_started",
                },
                indent=2,
            )
        )
        return 0
    result = run_comparison(config)
    directory = Path(config["results_root"]) / config["experiment_id"]
    atomic_json(directory / "proxy-comparison.json", result)
    (directory / "REPORT.md").write_text(render_report(result), encoding="utf-8")
    for profile_id, profile in result["profiles"].items():
        (directory / f"normalized-context-trends-{profile_id}.svg").write_text(
            render_trend_svg(profile["analysis"]), encoding="utf-8"
        )
    manifest = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    atomic_json(directory / "SHA256SUMS.json", manifest)
    print(json.dumps({"experiment_id": config["experiment_id"], "status": "completed"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
