"""Run Accelergy + McPAT for gem5 cache-energy estimation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from src.common.candidate import Candidate, ROOT
from src.common.errors import (
    ConfigError,
    MetricsError,
    PreflightError,
    RuntimeExecutionError,
)
from src.common.process import run_process
from src.common.security import digest, safe_id, within


ENERGY_SCOPE = (
    "Dynamic cache energy for two L1I caches, two L1D caches, "
    "and one shared L2 cache. Excludes processor-core logic, "
    "DRAM, interconnect, TLB, and static/leakage energy."
)


class EnergyEstimatorError(RuntimeExecutionError):
    """Raised when energy estimation cannot be completed."""


def cache_component(
    name: str,
    cache_type: str,
    configuration: dict,
) -> dict:
    return {
        "name": name,
        "class": "cache",
        "attributes": {
            "n_rd_ports": 1,
            "n_wr_ports": 1,
            "n_rdwr_ports": 1,
            "n_banks": 1,
            "cache_type": cache_type,
            "size": configuration["size_bytes"],
            "associativity": configuration["associativity"],
            "data_latency": configuration["data_latency_cycles"],
            "block_size": configuration["block_size_bytes"],
            "mshr_size": configuration["mshr_entries"],
            "tag_size": 64,
            "write_buffer_size": configuration[
                "write_buffer_entries"
            ],
        },
    }


def action_component(name: str, actions: dict) -> dict:
    return {
        "name": name,
        "action_counts": [
            {
                "name": action,
                "counts": count,
            }
            for action, count in actions.items()
        ],
    }


def build_accelergy_inputs(mapping: dict) -> tuple[dict, dict]:
    assumptions = mapping["mcpat_assumptions"]
    architecture_components = []
    action_components = []

    for core in mapping["cores"]:
        core_id = core["core_id"]

        for cache_name, cache_type in (
            ("l1i", "icache"),
            ("l1d", "dcache"),
        ):
            name = f"cpu{core_id}_{cache_name}"
            cache = core["caches"][cache_name]

            architecture_components.append(
                cache_component(
                    name,
                    cache_type,
                    cache["configuration"],
                )
            )
            action_components.append(
                action_component(
                    name,
                    cache["actions"],
                )
            )

    shared_l2 = mapping["shared_l2"]

    architecture_components.append(
        cache_component(
            "shared_l2",
            "l2cache",
            shared_l2["configuration"],
        )
    )
    action_components.append(
        action_component(
            "shared_l2",
            shared_l2["actions"],
        )
    )

    architecture = {
        "architecture": {
            "version": 0.3,
            "subtree": [
                {
                    "name": "qwen_attention_proxy",
                    "attributes": {
                        "technology": (
                            f"{assumptions['technology_nm']}nm"
                        ),
                        "datawidth": assumptions[
                            "datawidth_bits"
                        ],
                        "clockrate": assumptions[
                            "clockrate_mhz"
                        ],
                        "device_type": assumptions[
                            "device_type"
                        ],
                    },
                    "local": architecture_components,
                }
            ],
        }
    }

    action_counts = {
        "action_counts": {
            "version": 0.3,
            "subtree": [
                {
                    "name": "qwen_attention_proxy",
                    "local": action_components,
                }
            ],
        }
    }

    return architecture, action_counts


def write_yaml(path: Path, value: dict) -> None:
    path.write_text(
        yaml.safe_dump(
            value,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def run_accelergy(
    work_directory: Path,
    image: str,
    timeout_seconds: float = 300,
) -> str:
    docker = shutil.which("docker")
    if not docker:
        raise PreflightError("Docker is not installed on the energy worker.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:-]+", image):
        raise ConfigError("Invalid energy container image reference.")
    inspected = json.loads(
        run_process([docker, "image", "inspect", image], cwd=ROOT, timeout=min(timeout_seconds, 30))["stdout"]
    )[0]
    image_id = inspected["Id"]
    image_identity = (inspected.get("RepoDigests") or [image_id])[0]
    name = "chia-energy-" + safe_id(work_directory.name)
    command = [
        docker,
        "run",
        "--name",
        name,
        "--rm",
        "--pull=never",
        "--network=none",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=128",
        "-v",
        f"{work_directory.resolve()}:/work",
        "-w",
        "/work",
        image_id,
        "accelergy",
        "architecture.yaml",
        "action_counts.yaml",
        "-o",
        "output",
    ]

    if os.name != "nt":
        command[command.index("-v"):command.index("-v")] = [
            "--user", f"{os.getuid()}:{os.getgid()}"
        ]
    try:
        run_process(command, cwd=ROOT, timeout=timeout_seconds)
    finally:
        try:
            run_process([docker, "rm", "-f", name], cwd=ROOT, timeout=10)
        except Exception:
            pass
    return image_identity


def read_energy_uj(path: Path) -> tuple[float, list[dict]]:
    result = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    estimate = result["energy_estimation"]
    total_pj = float(estimate["Total"])

    if not math.isfinite(total_pj) or total_pj <= 0:
        raise EnergyEstimatorError(
            "Accelergy returned nonfinite or nonpositive energy."
        )

    return total_pj / 1_000_000.0, estimate["components"]


def update_metrics(
    source: Path,
    destination: Path,
    energy_uj: float,
) -> None:
    result = json.loads(
        source.read_text(encoding="utf-8")
    )

    metrics = result.get("metrics", result)
    metrics["energy_uj"] = energy_uj
    metrics["energy_scope"] = ENERGY_SCOPE

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    destination.write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )


def _stats(path: Path) -> dict[str, float]:
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) >= 2:
            try:
                value = float(fields[1])
            except ValueError:
                continue
            if math.isfinite(value):
                values[fields[0]] = value
    return values


def _counter(stats: dict[str, float], prefix: str, suffix: str) -> int:
    names = [
        f"{prefix}.{suffix}::total",
        f"{prefix}.{suffix}",
    ]
    for name in names:
        if name in stats:
            value = stats[name]
            if value < 0 or not value.is_integer():
                break
            return int(value)
    raise MetricsError(f"Required gem5 energy counter is missing: {prefix}.{suffix}.")


def build_energy_mapping(config: dict, hardware_result: dict, stats_path: Path) -> dict:
    """Join reviewed cache configuration to counters from this exact hardware run."""
    candidate = Candidate.from_dict(config)
    if (
        hardware_result.get("candidate_id") != candidate.candidate_id
        or hardware_result.get("hardware") != candidate.config["hardware"]
        or hardware_result.get("status") != "completed"
    ):
        raise MetricsError("Energy input does not belong to this completed candidate.")
    stats = _stats(stats_path)
    stats_sha256 = hashlib.sha256(stats_path.read_bytes()).hexdigest()
    expected_stats_sha256 = hardware_result.get("provenance", {}).get("stats_sha256")
    if expected_stats_sha256 and expected_stats_sha256 != stats_sha256:
        raise MetricsError("Hardware stats artifact changed after the gem5 run.")
    hw = candidate.config["hardware"]

    def cache(prefix: str, size: int, assoc: int, latency: int) -> dict:
        hits = _counter(stats, prefix, "overallHits")
        misses = _counter(stats, prefix, "overallMisses")
        return {
            "configuration": {
                "size_bytes": size * 1024,
                "associativity": assoc,
                "block_size_bytes": 64,
                "data_latency_cycles": latency,
                "tag_latency_cycles": latency,
                "response_latency_cycles": latency,
                "mshr_entries": 8,
                "write_buffer_entries": 8,
            },
            # gem5's aggregate counters do not distinguish reads from writes.
            # The estimator therefore models aggregate cache lookups as reads.
            "actions": {"read_hit": hits, "read_miss": misses, "write_hit": 0, "write_miss": 0},
        }

    cores = []
    for index in range(hw["cores"]):
        cpu = f"system.cpu{index}"
        cores.append({
            "core_id": index,
            "caches": {
                "l1i": cache(f"{cpu}.icache", hw["l1i_cache_kib"], hw["l1i_associativity"], hw["l1i_latency_cycles"]),
                "l1d": cache(f"{cpu}.dcache", hw["l1d_cache_kib"], hw["l1d_associativity"], hw["l1d_latency_cycles"]),
            },
        })
    return {
        "candidate_id": candidate.candidate_id,
        "hardware_result_id": digest(hardware_result),
        "stats_sha256": stats_sha256,
        "mcpat_assumptions": {
            "technology_nm": 45,
            "device_type": "lop",
            "clockrate_mhz": int(hw["frequency_ghz"] * 1000),
            "datawidth_bits": 64,
        },
        "cores": cores,
        "shared_l2": cache("system.l2cache", hw["l2_cache_kib"], hw["l2_associativity"], hw["l2_latency_cycles"]),
    }


def run_energy_candidate(config: dict, hardware_result: dict, runtime=None, context=None) -> dict:
    runtime = runtime or {}
    context = context or {}
    candidate = Candidate.from_dict(config)
    artifacts = hardware_result.get("artifacts", {})
    hardware_directory = Path(artifacts.get("directory", "")).resolve()
    stats_path = (hardware_directory / artifacts.get("stats", "")).resolve()
    try:
        stats_path.relative_to(hardware_directory)
    except ValueError as exc:
        raise MetricsError("Hardware stats path escapes its run directory.") from exc
    if not stats_path.is_file():
        raise MetricsError("Hardware stats artifact is missing.")
    mapping = build_energy_mapping(config, hardware_result, stats_path)
    run_id = safe_id(context.get("run_id", "local-" + candidate.candidate_id[:16]))
    root = Path(runtime.get("artifacts_root", ROOT / "results/energy")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    workdir = within(root, run_id)
    workdir.mkdir(exist_ok=False)
    architecture, actions = build_accelergy_inputs(mapping)
    write_yaml(workdir / "architecture.yaml", architecture)
    write_yaml(workdir / "action_counts.yaml", actions)
    (workdir / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    image_identity = run_accelergy(
        workdir,
        runtime.get("image", "chia-energy-tools:0.2"),
        timeout_seconds=runtime.get("timeout_seconds", 300),
    )
    result_path = workdir / "output/energy_estimation.yaml"
    if not result_path.is_file():
        raise EnergyEstimatorError("Accelergy result is missing.")
    energy_uj, components = read_energy_uj(result_path)
    return {
        "candidate_id": candidate.candidate_id,
        "status": "completed",
        "hardware_result_id": mapping["hardware_result_id"],
        "stats_sha256": mapping["stats_sha256"],
        "metrics": {"estimated_cache_dynamic_energy_uj": energy_uj},
        "scope": ENERGY_SCOPE,
        "provenance": {
            "estimator": "Accelergy with cache model inputs",
            "container_image_digest": image_identity,
            "assumptions": mapping["mcpat_assumptions"],
        },
        "artifacts": {"directory": str(workdir), "mapping": "mapping.json", "estimate": "output/energy_estimation.yaml"},
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mapping_json", type=Path)
    parser.add_argument("metrics_json", type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument(
        "--output-metrics",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--image",
        default="chia-energy-tools:0.2",
    )
    args = parser.parse_args()

    mapping = json.loads(
        args.mapping_json.read_text(encoding="utf-8")
    )
    architecture, action_counts = build_accelergy_inputs(
        mapping
    )

    args.workdir.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_yaml(
        args.workdir / "architecture.yaml",
        architecture,
    )
    write_yaml(
        args.workdir / "action_counts.yaml",
        action_counts,
    )

    run_accelergy(args.workdir, args.image)

    energy_path = (
        args.workdir
        / "output"
        / "energy_estimation.yaml"
    )

    if not energy_path.exists():
        raise EnergyEstimatorError(
            f"Missing Accelergy result: {energy_path}"
        )

    energy_uj, components = read_energy_uj(energy_path)

    update_metrics(
        args.metrics_json,
        args.output_metrics,
        energy_uj,
    )

    summary = {
        "energy_uj": energy_uj,
        "energy_scope": ENERGY_SCOPE,
        "components": components,
    }

    (args.workdir / "energy-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Energy: {energy_uj:.6f} uJ")
    print(f"Wrote metrics: {args.output_metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
