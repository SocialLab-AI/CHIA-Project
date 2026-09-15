import json
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

from chia.base.ChiaFunction import ChiaFunction

from src.hardware.knobs import (
    load_design_space,
    validate_hardware_candidate,
)


WORKER_PROJECT_ROOT = Path("/tmp/chia-project")
GEM5_WORKSPACE = Path("/tmp/chia-gem5-src")


def _run_gem5(hardware: dict[str, Any] | None = None) -> dict:
    """Run baseline or candidate hardware through the gem5 interface."""

    run_id = uuid.uuid4().hex[:8]

    runner = (
        WORKER_PROJECT_ROOT
        / "gem5"
        / "run_attention_experiment.py"
    )

    baseline_path = (
        WORKER_PROJECT_ROOT
        / "experiment-contracts"
        / "baselines"
        / "attention.yaml"
    )

    config = yaml.safe_load(
        baseline_path.read_text(encoding="utf-8")
    )

    if hardware is not None:
        design_space = load_design_space()
        validate_hardware_candidate(hardware, design_space)

        config["hardware"] = hardware
        config["metadata"]["experiment_id"] = (
            f"attn-q4-candidate-{run_id}"
        )
        config["metadata"]["description"] = (
            "Gemini-proposed hardware candidate evaluated in gem5."
        )

    config.pop("metrics", None)
    config["status"] = {
        "state": "planned",
        "message": "Waiting for gem5 execution.",
    }

    relative_outdir = f"results/chia-{run_id}"
    relative_output = f"{relative_outdir}/metrics.json"

    config_path = (
        WORKER_PROJECT_ROOT
        / "gem5"
        / relative_outdir
        / "candidate.yaml"
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    command = [
        sys.executable,
        str(runner),
        str(config_path),
        "--gem5-src",
        str(GEM5_WORKSPACE),
        "--outdir",
        relative_outdir,
        "--output",
        relative_output,
    ]

    process = subprocess.run(
        command,
        cwd=WORKER_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    metrics_path = (
        WORKER_PROJECT_ROOT
        / "gem5"
        / relative_output
    )

    result = json.loads(
        metrics_path.read_text(encoding="utf-8")
    )

    if result.get("status", {}).get("state") != "completed":
        raise RuntimeError(
            f"gem5 experiment did not complete: {result.get('status')}"
        )

    metrics = result.get("metrics")

    if not isinstance(metrics, dict):
        raise RuntimeError("gem5 result contains no metrics object")

    required_metrics = [
        "sim_ticks",
        "simulated_seconds",
        "latency_ms",
        "host_seconds",
        "instructions",
        "cycles_per_core",
        "ipc_per_core",
        "aggregate_ipc",
        "l1d_miss_rate_per_core",
        "l2_miss_rate",
    ]

    missing = [
        name for name in required_metrics
        if name not in metrics
    ]

    if missing:
        raise RuntimeError(
            f"gem5 result is missing required metrics: {missing}"
        )

    return {
        "run_id": run_id,
        "worker_hostname": socket.gethostname(),
        "status": result["status"],
        "hardware": result["hardware"],
        "workload": result["workload"],
        "software": result["software"],
        "metrics": metrics,
        "worker_config_path": str(config_path),
        "worker_metrics_path": str(metrics_path),
        "gem5_stdout_tail": process.stdout[-3000:],
    }


@ChiaFunction(resources={"gem5": 1}, num_cpus=1)
def run_gem5_baseline() -> dict:
    """Run the unchanged canonical gem5 baseline."""
    return _run_gem5()


@ChiaFunction(resources={"gem5": 1}, num_cpus=1)
def run_gem5_candidate(
    hardware: dict[str, Any],
) -> dict:
    """Run one validated Gemini-proposed hardware candidate."""
    return _run_gem5(hardware)
