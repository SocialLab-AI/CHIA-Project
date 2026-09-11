#!/usr/bin/env python3
"""Run the attention gem5 proxy from one config file and emit metrics."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import yaml

from extract_metrics import build_metrics, load_stats


DEFAULT_IMAGE = "ghcr.io/gem5/devcontainer:v25-1"
DEFAULT_WORKLOAD_SOURCE = "attention_kv.c"
DEFAULT_BINARY_NAME = "attention_kv_q4"
DEFAULT_GEM5_CONFIG = "attention-riscv.py"


def run(command, cwd=None):
    print("+ " + " ".join(str(part) for part in command))
    subprocess.run(command, cwd=cwd, check=True)


def load_config(path):
    with Path(path).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def require(config, *keys):
    current = config
    for key in keys:
        current = current[key]
    return current


def require_positive_int(config, *keys):
    value = require(config, *keys)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        path = ".".join(keys)
        raise ValueError(f"{path} must be a positive integer, got {value!r}")
    return value


def require_positive_number(config, *keys):
    value = require(config, *keys)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value <= 0
    ):
        path = ".".join(keys)
        raise ValueError(f"{path} must be positive, got {value!r}")
    return value


def validate_supported_config(config):
    kv_format = require(config, "software", "kv_format")
    if kv_format != "Q4":
        raise ValueError(
            f"this proxy currently supports kv_format=Q4, got {kv_format}"
        )

    threads = require_positive_int(config, "software", "threads")
    if threads != 2:
        raise ValueError(
            f"this proxy currently supports exactly 2 software threads, got {threads}"
        )

    layers = require_positive_int(config, "workload", "layers")
    if layers != 1:
        raise ValueError(
            f"this proxy currently supports workload.layers=1, got {layers}"
        )

    warmup_runs = require(config, "measurement", "warmup_runs")
    if warmup_runs != 0:
        raise ValueError(
            f"warmup runs are not implemented; expected 0, got {warmup_runs}"
        )

    head_dimension = require_positive_int(
        config, "workload", "head_dimension"
    )
    if head_dimension % 2 != 0:
        raise ValueError(
            "workload.head_dimension must be even for packed Q4 storage"
        )

    cpu_model = require(config, "hardware", "cpu_model")
    if cpu_model not in {"RiscvO3CPU", "RiscvTimingSimpleCPU"}:
        raise ValueError(f"unsupported hardware.cpu_model: {cpu_model}")

    cores = require_positive_int(config, "hardware", "cores")
    if threads > cores:
        raise ValueError(
            f"software.threads ({threads}) cannot exceed hardware.cores ({cores})"
        )

    issue_width = require_positive_int(
        config, "hardware", "issue_width"
    )
    if cpu_model == "RiscvTimingSimpleCPU" and issue_width != 1:
        raise ValueError(
            "RiscvTimingSimpleCPU requires hardware.issue_width=1"
        )

    require_positive_number(config, "hardware", "frequency_ghz")

    for field in (
        "l1i_cache_kib",
        "l1i_associativity",
        "l1i_latency_cycles",
        "l1d_cache_kib",
        "l1d_associativity",
        "l1d_latency_cycles",
        "l2_cache_kib",
        "l2_associativity",
        "l2_latency_cycles",
        "memory_size_mib",
    ):
        require_positive_int(config, "hardware", field)

    memory_type = require(config, "hardware", "memory_type")
    if memory_type != "DDR3_1600_8x8":
        raise ValueError(
            f"unsupported hardware.memory_type: {memory_type}"
        )

    simulation_mode = require(config, "hardware", "simulation_mode")
    if simulation_mode != "SE":
        raise ValueError(
            f"unsupported hardware.simulation_mode: {simulation_mode}"
        )


def workload_defines(config):
    return [
        f"-DCONTEXT={require_positive_int(config, 'workload', 'context_tokens')}",
        f"-DQUERY_HEADS={require_positive_int(config, 'workload', 'query_heads')}",
        f"-DKV_HEADS={require_positive_int(config, 'workload', 'kv_heads')}",
        f"-DHEAD_DIM={require_positive_int(config, 'workload', 'head_dimension')}",
        f"-DTHREADS={require_positive_int(config, 'software', 'threads')}",
        f"-DREPETITIONS={require_positive_int(config, 'measurement', 'repetitions')}",
    ]


def hardware_args(config):
    hardware = config["hardware"]

    return [
        "--cpu-model", str(hardware["cpu_model"]),
        "--cores", str(hardware["cores"]),
        "--frequency-ghz", str(hardware["frequency_ghz"]),
        "--issue-width", str(hardware["issue_width"]),
        "--l1i-cache-kib", str(hardware["l1i_cache_kib"]),
        "--l1i-associativity", str(hardware["l1i_associativity"]),
        "--l1i-latency-cycles", str(hardware["l1i_latency_cycles"]),
        "--l1d-cache-kib", str(hardware["l1d_cache_kib"]),
        "--l1d-associativity", str(hardware["l1d_associativity"]),
        "--l1d-latency-cycles", str(hardware["l1d_latency_cycles"]),
        "--l2-cache-kib", str(hardware["l2_cache_kib"]),
        "--l2-associativity", str(hardware["l2_associativity"]),
        "--l2-latency-cycles", str(hardware["l2_latency_cycles"]),
        "--memory-type", str(hardware["memory_type"]),
        "--memory-size-mib", str(hardware["memory_size_mib"]),
        "--simulation-mode", str(hardware["simulation_mode"]),
    ]


def build_binary(project_gem5_dir, gem5_src_dir, image, config):
    source = project_gem5_dir / DEFAULT_WORKLOAD_SOURCE
    target_source = gem5_src_dir / "attention_kv_q4.c"

    shutil.copy2(source, target_source)

    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{gem5_src_dir}:/gem5-src",
            "-w",
            "/gem5-src",
            image,
            "riscv64-linux-gnu-gcc",
            "-static",
            "-O2",
            "-std=c11",
            "-pthread",
            *workload_defines(config),
            "-o",
            DEFAULT_BINARY_NAME,
            "attention_kv_q4.c",
            "-lm",
        ]
    )


def run_gem5(project_gem5_dir, gem5_src_dir, image, outdir, config):
    outdir.mkdir(parents=True, exist_ok=True)

    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{project_gem5_dir}:/project/gem5",
            "-v",
            f"{gem5_src_dir}:/gem5-src",
            "-w",
            "/project/gem5",
            image,
            "gem5",
            f"--outdir=/project/gem5/{outdir.relative_to(project_gem5_dir)}",
            f"/project/gem5/{DEFAULT_GEM5_CONFIG}",
            *hardware_args(config),
        ]
    )


def write_metrics(config_path, outdir, output_path):
    stats_path = outdir / "stats.txt"
    config = load_config(config_path)

    config["metrics"] = build_metrics(load_stats(stats_path))
    config["status"] = {
        "state": "completed",
        "message": "gem5 run completed and metrics were extracted",
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote metrics: {output_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "config",
        type=Path,
        help="attention experiment YAML config",
    )

    parser.add_argument(
        "--gem5-src",
        type=Path,
        default=Path.home() / "gem5-src",
        help="host gem5 source directory mounted into Docker",
    )

    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help="Docker image containing gem5 and the RISC-V toolchain",
    )

    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("results/q4-baseline"),
        help="gem5 output directory relative to this gem5 folder",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/q4-baseline/metrics.json"),
        help="final metrics JSON output path",
    )

    args = parser.parse_args()

    project_gem5_dir = Path(__file__).resolve().parent
    gem5_src_dir = args.gem5_src.expanduser().resolve()
    config_path = args.config.resolve()
    outdir = (project_gem5_dir / args.outdir).resolve()
    output_path = (project_gem5_dir / args.output).resolve()

    config = load_config(config_path)
    validate_supported_config(config)

    build_binary(project_gem5_dir, gem5_src_dir, args.image, config)
    run_gem5(
        project_gem5_dir,
        gem5_src_dir,
        args.image,
        outdir,
        config,
    )
    write_metrics(config_path, outdir, output_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

