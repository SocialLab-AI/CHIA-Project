"""Deterministic gem5-statistics to Accelergy cache mapping."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

from src.common.candidate import Candidate
from src.common.errors import MetricsError
from src.common.security import digest


ENERGY_SCOPE = (
    "Dynamic cache energy for two L1I caches, two L1D caches, "
    "and one shared L2 cache. Excludes processor-core logic, "
    "DRAM, interconnect, TLB, and static/leakage energy."
)


def _stats(path: Path) -> dict[str, float]:
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        try:
            value = float(fields[1])
        except ValueError:
            continue
        if math.isfinite(value):
            values[fields[0]] = value
    return values


def _counter(stats: dict[str, float], prefix: str, suffix: str) -> int:
    for name in (f"{prefix}.{suffix}::total", f"{prefix}.{suffix}"):
        if name in stats:
            value = stats[name]
            if value >= 0 and value.is_integer():
                return int(value)
            break
    raise MetricsError(f"Required gem5 energy counter is missing: {prefix}.{suffix}.")


def build_energy_mapping(
    config: dict,
    hardware_result: dict,
    stats_path: Path,
) -> dict:
    """Join reviewed cache configuration to this exact gem5 run's counters."""
    candidate = Candidate.from_dict(config)
    if (
        hardware_result.get("candidate_id") != candidate.candidate_id
        or hardware_result.get("hardware") != candidate.config["hardware"]
        or hardware_result.get("status") != "completed"
    ):
        raise MetricsError("Energy input does not belong to this completed candidate.")

    stats = _stats(stats_path)
    stats_sha256 = hashlib.sha256(stats_path.read_bytes()).hexdigest()
    expected_stats_sha256 = hardware_result.get("provenance", {}).get(
        "stats_sha256"
    )
    if not expected_stats_sha256 or expected_stats_sha256 != stats_sha256:
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
            # The available aggregate counters do not split reads and writes.
            "actions": {
                "read_hit": hits,
                "read_miss": misses,
                "write_hit": 0,
                "write_miss": 0,
            },
        }

    cores = []
    for index in range(hw["cores"]):
        cpu = f"system.cpu{index}"
        cores.append(
            {
                "core_id": index,
                "caches": {
                    "l1i": cache(
                        f"{cpu}.icache",
                        hw["l1i_cache_kib"],
                        hw["l1i_associativity"],
                        hw["l1i_latency_cycles"],
                    ),
                    "l1d": cache(
                        f"{cpu}.dcache",
                        hw["l1d_cache_kib"],
                        hw["l1d_associativity"],
                        hw["l1d_latency_cycles"],
                    ),
                },
            }
        )

    return {
        "candidate_id": candidate.candidate_id,
        "hardware_result_id": digest(hardware_result),
        "stats_sha256": stats_sha256,
        "energy_scope": ENERGY_SCOPE,
        "mcpat_assumptions": {
            "technology_nm": 45,
            "device_type": "lop",
            "clockrate_mhz": int(hw["frequency_ghz"] * 1000),
            "datawidth_bits": 64,
        },
        "cores": cores,
        "shared_l2": cache(
            "system.l2cache",
            hw["l2_cache_kib"],
            hw["l2_associativity"],
            hw["l2_latency_cycles"],
        ),
    }
