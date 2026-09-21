"""Run Accelergy + McPAT for gem5 cache-energy estimation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import time
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
from src.common.security import safe_id, within
from src.hardware.energy_mapping import ENERGY_SCOPE, build_energy_mapping


REQUIRED_COMPONENTS = {
    "cpu0_l1i",
    "cpu0_l1d",
    "cpu1_l1i",
    "cpu1_l1d",
    "shared_l2",
}


class EnergyEstimatorError(RuntimeExecutionError):
    """Raised when energy estimation cannot be completed."""


def preflight_energy_runtime(runtime: dict, timeout_seconds: float) -> dict:
    """Validate the local Docker image and writable artifact root before gem5."""
    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        error = PreflightError("Energy timeout must be positive.")
        error.runtime_stage = "energy_preflight"
        raise error
    image = runtime.get("image", "chia-energy-tools:0.3")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:-]+", image):
        error = ConfigError("Invalid energy container image reference.")
        error.runtime_stage = "energy_preflight"
        raise error
    docker = shutil.which("docker")
    if not docker:
        error = PreflightError("Docker is not installed on the hardware worker.")
        error.runtime_stage = "energy_preflight"
        raise error
    root = Path(runtime.get("artifacts_root", ROOT / "results/energy")).resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".chia-energy-write-probe"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        error = PreflightError("Energy artifact root is not writable.")
        error.runtime_stage = "energy_preflight"
        raise error from exc
    try:
        inspected = json.loads(
            run_process(
                [docker, "image", "inspect", image],
                cwd=ROOT,
                timeout=min(timeout_seconds, 30),
            )["stdout"]
        )[0]
    except Exception as exc:
        error = PreflightError(f"Required energy image is unavailable: {image}")
        error.runtime_stage = "energy_preflight"
        raise error from exc
    labels = inspected.get("Config", {}).get("Labels") or {}
    required_labels = {
        "org.chia.accelergy.version",
        "org.chia.accelergy.commit",
        "org.chia.accelergy-mcpat-plugin.commit",
        "org.chia.mcpat.version",
        "org.chia.mcpat.commit",
    }
    if any(not labels.get(name) for name in required_labels):
        error = PreflightError(
            "Energy image is missing required pinned tool provenance labels."
        )
        error.runtime_stage = "energy_preflight"
        raise error
    return {"docker": docker, "image": image, "inspection": inspected}


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
    image_preflight: dict | None = None,
) -> dict:
    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        raise ConfigError("Energy timeout must be positive.")
    deadline = time.monotonic() + timeout_seconds

    def remaining() -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            from src.common.errors import ExecutionTimeout

            error = ExecutionTimeout("Energy-estimation deadline expired.")
            error.runtime_stage = "energy_execution"
            raise error
        return value

    if image_preflight is None:
        image_preflight = preflight_energy_runtime(
            {"image": image, "artifacts_root": work_directory.parent},
            remaining(),
        )
    if image_preflight.get("image") != image:
        error = PreflightError("Energy image preflight does not match execution.")
        error.runtime_stage = "energy_preflight"
        raise error
    docker = image_preflight["docker"]
    inspected = image_preflight["inspection"]
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
        "chia-accelergy",
        "-o",
        "output",
        "architecture.yaml",
        "action_counts.yaml",
    ]

    if os.name != "nt":
        command[command.index("-v"):command.index("-v")] = [
            "--user", f"{os.getuid()}:{os.getgid()}"
        ]
    result = None
    started = time.monotonic()
    try:
        try:
            result = run_process(command, cwd=ROOT, timeout=remaining())
        except Exception as error:
            error.runtime_stage = "energy_execution"
            raise
    finally:
        try:
            run_process([docker, "rm", "-f", name], cwd=ROOT, timeout=10)
        except Exception:
            pass
    estimate = work_directory / "output/energy_estimation.yaml"
    if not estimate.is_file():
        error = EnergyEstimatorError(
            "Accelergy completed without creating energy_estimation.yaml."
        )
        error.runtime_stage = "energy_verification"
        error.stdout_summary = result["stdout_summary"]
        error.stderr_summary = result["stderr_summary"]
        raise error
    labels = inspected.get("Config", {}).get("Labels") or {}
    return {
        "container_image_digest": image_identity,
        "container_image_id": image_id,
        "accelergy_version": labels.get("org.chia.accelergy.version"),
        "accelergy_commit": labels.get("org.chia.accelergy.commit"),
        "mcpat_version": labels.get("org.chia.mcpat.version"),
        "mcpat_commit": labels.get("org.chia.mcpat.commit"),
        "plugin_commit": labels.get("org.chia.accelergy-mcpat-plugin.commit"),
        "execution_duration_seconds": time.monotonic() - started,
    }


def read_energy_uj(path: Path) -> tuple[float, list[dict]]:
    try:
        result = yaml.safe_load(path.read_text(encoding="utf-8"))
        estimate = result["energy_estimation"]
        total_pj = float(estimate["Total"])
        components = estimate["components"]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise EnergyEstimatorError(
            "Accelergy output is missing required total or component evidence."
        ) from exc

    if not math.isfinite(total_pj) or total_pj <= 0:
        raise EnergyEstimatorError(
            "Accelergy returned nonfinite or nonpositive energy."
        )

    if not isinstance(components, list):
        raise EnergyEstimatorError("Accelergy components must be a list.")
    return total_pj / 1_000_000.0, components


def verify_components(components: list[dict]) -> None:
    if len(components) != len(REQUIRED_COMPONENTS):
        raise EnergyEstimatorError(
            "Accelergy output must contain exactly five cache components."
        )
    names = set()
    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get("name"), str):
            raise EnergyEstimatorError("Accelergy returned a malformed component.")
        try:
            value = float(component["energy"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EnergyEstimatorError(
                "Accelergy component energy is missing or malformed."
            ) from exc
        if not math.isfinite(value) or value < 0:
            raise EnergyEstimatorError(
                "Accelergy component energy is negative or nonfinite."
            )
        names.add(component["name"].split(".")[-1])
    if names != REQUIRED_COMPONENTS:
        raise EnergyEstimatorError(
            "Accelergy output does not contain the five required cache components."
        )


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


def run_energy_candidate(config: dict, hardware_result: dict, runtime=None, context=None) -> dict:
    runtime = runtime or {}
    context = context or {}
    candidate = Candidate.from_dict(config)
    artifacts = hardware_result.get("artifacts", {})
    hardware_directory = Path(artifacts.get("directory", "")).resolve()
    allowed_hardware_root = Path(
        runtime.get("hardware_artifacts_root", hardware_directory.parent)
    ).resolve()
    try:
        hardware_directory.relative_to(allowed_hardware_root)
    except ValueError as exc:
        error = MetricsError("Hardware artifact directory escapes its allowed root.")
        error.runtime_stage = "energy_preflight"
        raise error from exc
    stats_path = (hardware_directory / artifacts.get("stats", "")).resolve()
    try:
        stats_path.relative_to(hardware_directory)
    except ValueError as exc:
        raise MetricsError("Hardware stats path escapes its run directory.") from exc
    if not stats_path.is_file():
        raise MetricsError("Hardware stats artifact is missing.")
    try:
        mapping = build_energy_mapping(config, hardware_result, stats_path)
    except Exception as error:
        error.runtime_stage = "energy_mapping"
        raise
    run_id = safe_id(context.get("run_id", "local-" + candidate.candidate_id[:16]))
    root = Path(runtime.get("artifacts_root", ROOT / "results/energy")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        error = PreflightError("Energy artifact root is not a directory.")
        error.runtime_stage = "energy_preflight"
        raise error
    workdir = within(root, run_id)
    workdir.mkdir(exist_ok=False)
    try:
        probe = workdir / ".write-probe"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        error = PreflightError("Energy artifact directory is not writable.")
        error.runtime_stage = "energy_preflight"
        raise error from exc
    architecture, actions = build_accelergy_inputs(mapping)
    write_yaml(workdir / "architecture.yaml", architecture)
    write_yaml(workdir / "action_counts.yaml", actions)
    (workdir / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    timeout = runtime.get("timeout_seconds", 300)
    if "deadline_epoch_seconds" in runtime:
        timeout = min(timeout, runtime["deadline_epoch_seconds"] - time.time())
    if timeout <= 0:
        from src.common.errors import ExecutionTimeout

        error = ExecutionTimeout("Hardware deadline expired before Accelergy.")
        error.runtime_stage = "energy_execution"
        raise error
    image_provenance = run_accelergy(
        workdir,
        runtime.get("image", "chia-energy-tools:0.3"),
        timeout_seconds=timeout,
        image_preflight=runtime.get("_image_preflight"),
    )
    result_path = workdir / "output/energy_estimation.yaml"
    if not result_path.is_file():
        raise EnergyEstimatorError("Accelergy result is missing.")
    try:
        energy_uj, components = read_energy_uj(result_path)
        verify_components(components)
    except Exception as error:
        error.runtime_stage = "energy_verification"
        raise
    hashes = {
        name: hashlib.sha256((workdir / relative).read_bytes()).hexdigest()
        for name, relative in {
            "mapping_sha256": "mapping.json",
            "architecture_sha256": "architecture.yaml",
            "action_counts_sha256": "action_counts.yaml",
            "energy_result_sha256": "output/energy_estimation.yaml",
        }.items()
    }
    return {
        "candidate_id": candidate.candidate_id,
        "status": "completed",
        "hardware_result_id": mapping["hardware_result_id"],
        "stats_sha256": mapping["stats_sha256"],
        "metrics": {"estimated_cache_dynamic_energy_uj": energy_uj},
        "scope": ENERGY_SCOPE,
        "provenance": {
            "estimator": "Accelergy with cache model inputs",
            **image_provenance,
            **hashes,
            "assumptions": mapping["mcpat_assumptions"],
            "energy_scope": ENERGY_SCOPE,
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
        default="chia-energy-tools:0.3",
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
