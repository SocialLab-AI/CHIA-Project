#!/usr/bin/env python3
"""Collect and analyze Issue #60 Qwen-to-gem5 proxy-fidelity evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

import yaml

from src.common.candidate import Candidate, ROOT, baseline_candidate
from src.common.errors import ConfigError, ExecutionTimeout, PreflightError
from src.common.records import atomic_json
from src.common.security import safe_id, within
from src.hardware.proxy_fidelity import (
    CONTEXT_LENGTHS,
    analyze_fidelity,
    render_report,
    render_trend_svg,
)
from src.hardware.runner import run_gem5_candidate
from src.tutor.benchmark import run_native_context_sweep
from src.tutor.model_profile import extract_gguf_profile


def load_config(path):
    """Validate operator paths and fixed calibration protocol before execution."""

    source = Path(path).resolve()
    value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigError("Proxy-fidelity configuration must be a YAML object.")
    required = {"experiment_id", "contexts", "results_root", "native", "hardware"}
    if set(value) != required:
        raise ConfigError("Proxy-fidelity configuration fields are incomplete or unknown.")
    value["experiment_id"] = safe_id(value["experiment_id"])
    if tuple(value["contexts"]) != CONTEXT_LENGTHS:
        raise ConfigError("Issue #60 requires contexts 128, 256, 512, 1024 and 2048.")
    results_root = Path(value["results_root"])
    if results_root.is_absolute():
        raise ConfigError("results_root must be repository-relative.")
    value["results_root"] = str(within(ROOT, value["results_root"]))

    native = value["native"]
    native_required = {
        "model_path",
        "model_sha256",
        "llama_bench",
        "threads",
        "repetitions",
        "timeout_seconds",
        "collect_perf",
    }
    if not isinstance(native, dict) or set(native) != native_required:
        raise ConfigError("Native calibration settings are incomplete or unknown.")
    if not isinstance(native["model_path"], str) or not native["model_path"].strip():
        raise ConfigError("native.model_path must be nonempty text.")
    if not isinstance(native["llama_bench"], str) or not native["llama_bench"].strip():
        raise ConfigError("native.llama_bench must be nonempty text.")
    if not isinstance(native["model_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", native["model_sha256"]
    ):
        raise ConfigError("native.model_sha256 must be one SHA-256 digest.")
    if not isinstance(native["collect_perf"], bool):
        raise ConfigError("native.collect_perf must be boolean.")
    for field in ("threads", "repetitions", "timeout_seconds"):
        if type(native[field]) is not int or native[field] < 1:
            raise ConfigError(f"native.{field} must be a positive integer.")
    if native["repetitions"] < 2:
        raise ConfigError("native.repetitions must be at least two.")

    hardware = value["hardware"]
    hardware_required = {
        "mode",
        "ray_address",
        "image",
        "timeout_seconds",
        "correctness_tolerance",
        "sensitivity",
    }
    if not isinstance(hardware, dict) or set(hardware) != hardware_required:
        raise ConfigError("Hardware calibration settings are incomplete or unknown.")
    if hardware["mode"] not in {"local", "chia"}:
        raise ConfigError("hardware.mode must be local or chia.")
    if not isinstance(hardware["ray_address"], str) or not hardware[
        "ray_address"
    ].strip():
        raise ConfigError("hardware.ray_address must be nonempty text.")
    if not isinstance(hardware["image"], str) or not hardware["image"].strip():
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
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or number < 0
        ):
            raise ConfigError(f"hardware.correctness_tolerance.{name} is invalid.")
    if not isinstance(hardware["sensitivity"], list):
        raise ConfigError("hardware.sensitivity must be a list.")
    case_ids = set()
    for case in hardware["sensitivity"]:
        if not isinstance(case, dict) or set(case) != {"case_id", "hardware_overrides"}:
            raise ConfigError("Each sensitivity case requires case_id and hardware_overrides.")
        case_id = safe_id(case["case_id"])
        if case_id == "baseline" or case_id in case_ids:
            raise ConfigError("Sensitivity case IDs must be unique and not baseline.")
        case_ids.add(case_id)
        if not isinstance(case["hardware_overrides"], dict):
            raise ConfigError("hardware_overrides must be an object.")
        candidate = copy.deepcopy(baseline_candidate())
        candidate["workload"]["context_tokens"] = 512
        candidate["hardware"].update(case["hardware_overrides"])
        Candidate.from_dict(candidate)
    return value


def _directory(config):
    directory = Path(config["results_root"]) / config["experiment_id"]
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect_profile(config):
    directory = _directory(config)
    native = config["native"]
    profile = extract_gguf_profile(native["model_path"], native["model_sha256"])
    atomic_json(directory / "model-profile.json", profile)
    return profile


def collect_native(config):
    directory = _directory(config)
    native = config["native"]
    result = run_native_context_sweep(
        model_path=native["model_path"],
        expected_sha256=native["model_sha256"],
        llama_bench=native["llama_bench"],
        contexts=config["contexts"],
        threads=native["threads"],
        repetitions=native["repetitions"],
        timeout_seconds=native["timeout_seconds"],
        collect_perf=native["collect_perf"],
    )
    atomic_json(directory / "native-context-sweep.json", result)
    return result


def _run_hardware_cases(cases, runtime, mode, ray_address):
    if mode == "local":
        results = []
        for index, (run_id, candidate) in enumerate(cases, start=1):
            print(f"[hardware {index}/{len(cases)}] {run_id} starting", flush=True)
            results.append(
                run_gem5_candidate(candidate, runtime, {"run_id": run_id})
            )
            print(f"[hardware {index}/{len(cases)}] {run_id} completed", flush=True)
        return results
    try:
        import ray
        from chia.base.ChiaFunction import ChiaFunction, chia_cancel
    except ImportError as error:
        raise PreflightError("Install the cluster extra before CHIA calibration.") from error
    if not ray.is_initialized():
        ray.init(address=ray_address)
    if ray.cluster_resources().get("gem5", 0) < 1:
        raise PreflightError("The CHIA cluster has no gem5 worker resource.")
    node = ChiaFunction(
        resources={"gem5": 1},
        num_cpus=1,
        max_retries=0,
        retry_exceptions=False,
    )(run_gem5_candidate)
    results = []
    for index, (run_id, candidate) in enumerate(cases, start=1):
        print(f"[hardware {index}/{len(cases)}] {run_id} submitted", flush=True)
        reference = node.chia_remote(candidate, runtime, {"run_id": run_id})
        try:
            results.append(ray.get(reference, timeout=runtime["timeout_seconds"] + 30))
            print(f"[hardware {index}/{len(cases)}] {run_id} completed", flush=True)
        except ray.exceptions.GetTimeoutError as error:
            chia_cancel(reference, force=True)
            raise ExecutionTimeout("gem5 calibration case exceeded its deadline.") from error
    return results


def collect_hardware(config):
    directory = _directory(config)
    settings = config["hardware"]
    runtime = {
        "image": settings["image"],
        "timeout_seconds": settings["timeout_seconds"],
        "retries": 0,
        "correctness_tolerance": settings["correctness_tolerance"],
    }
    timestamp = int(time.time())
    context_cases = []
    for context_tokens in config["contexts"]:
        candidate = baseline_candidate()
        candidate["workload"]["context_tokens"] = context_tokens
        candidate = Candidate.from_dict(candidate).config
        run_id = safe_id(
            f"proxy60-context-{context_tokens}-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
        context_cases.append((run_id, candidate))
    context_results = _run_hardware_cases(
        context_cases,
        runtime,
        settings["mode"],
        settings["ray_address"],
    )
    contexts = [
        {
            "context_tokens": candidate["workload"]["context_tokens"],
            "candidate_id": result["candidate_id"],
            "metrics": result["metrics"],
            "correctness": result["correctness"],
            "provenance": result["provenance"],
            "artifacts": result["artifacts"],
        }
        for (_, candidate), result in zip(context_cases, context_results)
    ]

    baseline_512 = next(item for item in contexts if item["context_tokens"] == 512)
    sensitivity = [
        {
            "case_id": "baseline",
            "candidate_id": baseline_512["candidate_id"],
            "hardware": baseline_candidate()["hardware"],
            "metrics": baseline_512["metrics"],
            "correctness": baseline_512["correctness"],
            "provenance": baseline_512["provenance"],
        }
    ]
    sensitivity_cases = []
    sensitivity_ids = []
    for case in settings["sensitivity"]:
        candidate = copy.deepcopy(baseline_candidate())
        candidate["workload"]["context_tokens"] = 512
        candidate["hardware"].update(case["hardware_overrides"])
        candidate = Candidate.from_dict(candidate).config
        run_id = safe_id(
            f"proxy60-{case['case_id']}-{timestamp}-{uuid.uuid4().hex[:8]}"
        )
        sensitivity_cases.append((run_id, candidate))
        sensitivity_ids.append(case["case_id"])
    sensitivity_results = _run_hardware_cases(
        sensitivity_cases,
        runtime,
        settings["mode"],
        settings["ray_address"],
    )
    for case_id, (_, candidate), result in zip(
        sensitivity_ids, sensitivity_cases, sensitivity_results
    ):
        sensitivity.append(
            {
                "case_id": case_id,
                "candidate_id": result["candidate_id"],
                "hardware": candidate["hardware"],
                "metrics": result["metrics"],
                "correctness": result["correctness"],
                "provenance": result["provenance"],
            }
        )
    evidence = {
        "schema_version": "0.1.0",
        "kind": "gem5_proxy_fidelity_sweep",
        "contexts": contexts,
        "sensitivity": sensitivity,
        "measurement_scope": "Q4 attention proxy, not complete Qwen inference",
    }
    atomic_json(directory / "gem5-proxy-sweep.json", evidence)
    return evidence


def analyze(config):
    directory = _directory(config)
    model = _read_json(directory / "model-profile.json")
    native = _read_json(directory / "native-context-sweep.json")
    hardware = _read_json(directory / "gem5-proxy-sweep.json")
    result = analyze_fidelity(model, native, hardware)
    atomic_json(directory / "analysis.json", result)
    (directory / "normalized-context-trends.svg").write_text(
        render_trend_svg(result), encoding="utf-8"
    )
    (directory / "REPORT.md").write_text(
        render_report(result, model), encoding="utf-8"
    )
    manifest = {}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.json":
            manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    atomic_json(directory / "SHA256SUMS.json", manifest)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--phase",
        choices=("profile", "native", "hardware", "analyze", "all"),
        default="all",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    phases = (
        ("profile", "native", "hardware", "analyze")
        if args.phase == "all"
        else (args.phase,)
    )
    outputs = {}
    for phase in phases:
        print(f"[phase] {phase} starting", flush=True)
        outputs[phase] = {
            "profile": collect_profile,
            "native": collect_native,
            "hardware": collect_hardware,
            "analyze": analyze,
        }[phase](config)
        print(f"[phase] {phase} completed", flush=True)
    print(json.dumps({"experiment_id": config["experiment_id"], "phases": list(outputs)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
