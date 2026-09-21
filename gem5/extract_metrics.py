#!/usr/bin/env python3
"""Merge gem5 stats into an attention experiment and validate the result."""

import argparse
import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def load_stats(path):
    stats = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith("-"):
            continue

        try:
            stats[parts[0]] = float(parts[1])
        except ValueError:
            continue

    return stats


def required(stats, *names):
    for name in names:
        if name in stats:
            return stats[name]

    raise KeyError(f"missing gem5 statistic; tried: {', '.join(names)}")


def per_core(stats, suffix):
    found = []
    pattern = re.compile(rf"^system\.cpu(\d+)\.{re.escape(suffix)}$")

    for name, value in stats.items():
        match = pattern.match(name)
        if match:
            found.append((int(match.group(1)), value))

    if not found:
        raise KeyError(f"missing per-core gem5 statistic: {suffix}")

    return [value for _, value in sorted(found)]


def integer(value):
    return int(round(value))


def build_metrics(stats):
    cycles = [integer(value) for value in per_core(stats, "numCycles")]
    instructions = integer(required(stats, "simInsts"))

    simulated_seconds = required(stats, "simSeconds")
    tick_frequency = stats.get("simFreq", 1_000_000_000_000.0)

    average_memory_latency_ticks = required(
        stats,
        "system.mem_ctrl.dram.avgMemAccLat",
    )

    average_read_bandwidth = required(
        stats,
        "system.mem_ctrl.dram.avgRdBW",
    )

    average_write_bandwidth = stats.get(
        "system.mem_ctrl.dram.avgWrBW",
        0.0,
    )

    peak_bandwidth = required(
        stats,
        "system.mem_ctrl.dram.peakBW",
    )

    return {
        "sim_ticks": integer(required(stats, "simTicks")),
        "simulated_seconds": simulated_seconds,
        "latency_ms": simulated_seconds * 1000.0,
        "host_seconds": required(stats, "hostSeconds"),
        "instructions": instructions,
        "cycles_per_core": cycles,
        "cpi_per_core": per_core(stats, "cpi"),
        "ipc_per_core": per_core(stats, "ipc"),
        "aggregate_ipc": instructions / max(cycles),
        "l1i_miss_rate_per_core": per_core(
            stats,
            "icache.overallMissRate::total",
        ),
        "l1d_miss_rate_per_core": per_core(
            stats,
            "dcache.overallMissRate::total",
        ),
        "l2_miss_rate": required(
            stats,
            "system.l2cache.overallMissRate::total",
        ),
        "dram_bytes_read": integer(
            required(
                stats,
                "system.mem_ctrl.dram.bytesRead::total",
                "system.mem_ctrl.dram.dramBytesRead",
            )
        ),
        "dram_bytes_written": integer(
            required(
                stats,
                "system.mem_ctrl.dram.dramBytesWritten",
                "system.mem_ctrl.bytesWrittenSys",
            )
        ),
        "dram_bandwidth_bytes_per_second": required(
            stats,
            "system.mem_ctrl.dram.bwTotal::total",
        ),
        "dram_bandwidth_utilization_percent": (
            (average_read_bandwidth + average_write_bandwidth)
            / peak_bandwidth
            * 100.0
        ),
        "average_dram_access_latency_ns": (
            average_memory_latency_ticks
            / tick_frequency
            * 1_000_000_000.0
        ),
        "energy_uj": None,
        "energy_scope": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("stats", type=Path, help="gem5 stats.txt")
    parser.add_argument("experiment", type=Path, help="input YAML/JSON experiment")

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("completed.attention.json"),
    )

    parser.add_argument(
        "--schema",
        type=Path,
        default=(
            Path(__file__).resolve().parent.parent
            / "experiment-contracts"
            / "schemas"
            / "chia-experiment.schema.yaml"
        ),
    )

    args = parser.parse_args()

    with args.experiment.open(encoding="utf-8") as stream:
        experiment = yaml.safe_load(stream)

    experiment["metrics"] = build_metrics(load_stats(args.stats))
    experiment["status"] = {
        "state": "completed",
        "message": "gem5 metrics extracted successfully from stats.txt",
    }

    raw_schema = yaml.safe_load(args.schema.read_text(encoding="utf-8"))
    if "$defs" in raw_schema and "attention_experiment" in raw_schema["$defs"]:
        schema = {
            "$schema": raw_schema.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
            "$ref": "#/$defs/attention_experiment",
            "$defs": raw_schema["$defs"],
        }
    else:
        schema = raw_schema

    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(experiment),
        key=lambda error: list(error.path),
    )

    if errors:
        for error in errors:
            location = "/" + "/".join(str(item) for item in error.path)
            print(f"INVALID {location}: {error.message}")

        return 1

    args.output.write_text(
        json.dumps(experiment, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"VALID: wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
