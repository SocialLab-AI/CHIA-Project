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


def ensure_q4(config):
    kv_format = require(config, "software", "kv_format")
    if kv_format != "Q4":
        raise ValueError(
            f"this proxy currently supports kv_format=Q4, got {kv_format}"
        )


def build_binary(project_gem5_dir, gem5_src_dir, image):
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
            "-o",
            DEFAULT_BINARY_NAME,
            "attention_kv_q4.c",
            "-lm",
        ]
    )


def run_gem5(project_gem5_dir, gem5_src_dir, image, outdir):
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
    ensure_q4(config)

    build_binary(project_gem5_dir, gem5_src_dir, args.image)
    run_gem5(project_gem5_dir, gem5_src_dir, args.image, outdir)
    write_metrics(config_path, outdir, output_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

