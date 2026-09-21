#!/usr/bin/env python3
"""Fail-closed release preflight for the CHIA head and gem5 worker."""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.candidate import ROOT, baseline_candidate
from src.common.errors import ConfigError, PreflightError
from src.hardware.energy_estimator import (
    build_accelergy_inputs,
    read_energy_uj,
    run_accelergy,
    write_yaml,
)
from src.orchestration.chia import validate_campaign_config
from src.tutor.llama_cpp_runtime import preflight as runtime_preflight
from src.tutor.mapping import map_final_tutor


def _synthetic_energy_mapping():
    cache = {
        "configuration": {
            "size_bytes": 32 * 1024,
            "associativity": 4,
            "block_size_bytes": 64,
            "data_latency_cycles": 2,
            "tag_latency_cycles": 2,
            "response_latency_cycles": 2,
            "mshr_entries": 8,
            "write_buffer_entries": 8,
        },
        "actions": {
            "read_hit": 100,
            "read_miss": 10,
            "write_hit": 0,
            "write_miss": 0,
        },
    }
    return {
        "mcpat_assumptions": {
            "technology_nm": 45,
            "device_type": "lop",
            "clockrate_mhz": 1000,
            "datawidth_bits": 64,
        },
        "cores": [
            {
                "core_id": index,
                "caches": {"l1i": cache, "l1d": cache},
            }
            for index in range(2)
        ],
        "shared_l2": cache,
    }


def check_head(config):
    software_runtime = config["runtime"]["software"]
    permission_name = software_runtime.get("dataset_permission_env")
    if permission_name and os.getenv(permission_name) != "1":
        raise ConfigError(
            f"Set {permission_name}=1 only after OpenStax permission is confirmed."
        )
    mapping = map_final_tutor(
        baseline_candidate()["software"],
        software_runtime,
    )
    identity = runtime_preflight(
        mapping["endpoint"],
        mapping,
        timeout=15,
    )
    return {
        "role": "CHIA head node",
        "python_version": platform.python_version(),
        "model_path": identity["model_path"],
        "model_sha256": identity["model_sha256"],
        "context_tokens": identity["context_tokens"],
        "parallel_slots": identity["parallel_slots"],
        "runtime_build": identity["runtime_build"],
    }


def check_worker(config):
    import ray

    resources = ray.cluster_resources()
    for resource in ("control", "llama_cpp", "gem5"):
        if resources.get(resource, 0) < 1:
            raise PreflightError(f"Ray cluster lacks required {resource} resource.")

    hardware_image = config["runtime"]["hardware"]["image"]
    energy_image = config["runtime"]["energy"]["image"]

    @ray.remote(resources={"gem5": 1}, num_cpus=1)
    def worker_probe(hardware_image, energy_image):
        docker = shutil.which("docker")
        uv = shutil.which("uv")
        if not docker or not uv:
            raise RuntimeError("gem5 worker requires docker and uv on PATH.")

        images = {}
        for image in (hardware_image, energy_image):
            result = subprocess.run(
                [docker, "image", "inspect", image],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(f"Required worker image is unavailable: {image}")
            inspected = json.loads(result.stdout)[0]
            images[image] = (inspected.get("RepoDigests") or [inspected["Id"]])[0]

        with tempfile.TemporaryDirectory(prefix="chia-energy-preflight-") as directory:
            workdir = Path(directory)
            architecture, actions = build_accelergy_inputs(
                _synthetic_energy_mapping()
            )
            write_yaml(workdir / "architecture.yaml", architecture)
            write_yaml(workdir / "action_counts.yaml", actions)
            energy_identity = run_accelergy(
                workdir,
                energy_image,
                timeout_seconds=120,
            )
            result_path = workdir / "output/energy_estimation.yaml"
            if not result_path.is_file():
                raise RuntimeError("Energy preflight did not create its estimate.")
            energy_uj, _components = read_energy_uj(result_path)

        return {
            "role": "gem5 worker",
            "python_version": platform.python_version(),
            "uv": uv,
            "docker": docker,
            "images": images,
            "energy_image_identity": energy_identity,
            "synthetic_cache_dynamic_energy_uj": energy_uj,
        }

    return ray.get(worker_probe.remote(hardware_image, energy_image), timeout=180)


def initialize_ray(config):
    """Connect and package this checkout for repository-free workers."""
    import ray

    if not ray.is_initialized():
        ray.init(
            address=config.get("ray_address", "auto"),
            runtime_env={"working_dir": str(ROOT)},
        )
    return ray


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("experiment-contracts/campaigns/final-burst.yaml"),
    )
    parser.add_argument("--head-only", action="store_true")
    args = parser.parse_args()

    config = validate_campaign_config(
        yaml.safe_load(args.config.read_text(encoding="utf-8"))
    )
    result = {"status": "passed", "head": check_head(config)}

    if not args.head_only:
        ray = initialize_ray(config)
        try:
            result["worker"] = check_worker(config)
        finally:
            ray.shutdown()

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
