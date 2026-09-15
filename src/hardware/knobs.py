from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_DESIGN_SPACE = (
    Path(__file__).resolve().parents[2]
    / "experiment-contracts"
    / "design-spaces"
    / "hardware.yaml"
)


class HardwareConfigError(ValueError):
    pass


def load_design_space(path: Path = DEFAULT_DESIGN_SPACE) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def baseline_hardware_candidate(
    design_space: dict[str, Any],
) -> dict[str, Any]:
    baseline = design_space["baseline"]
    active = design_space["active_candidates"]["hardware"]
    fixed = design_space["fixed"]

    candidate = {
        knob: baseline[knob]
        for knob in active
    }

    candidate.update(
        {
            key: value
            for key, value in fixed.items()
            if key
            in {
                "cores",
                "l1i_cache_kib",
                "l1i_associativity",
                "l1i_latency_cycles",
                "l1d_latency_cycles",
                "l2_latency_cycles",
                "memory_type",
                "memory_size_mib",
                "simulation_mode",
            }
        }
    )

    return candidate


def validate_hardware_candidate(
    candidate: dict[str, Any],
    design_space: dict[str, Any],
) -> None:
    active = design_space["active_candidates"]["hardware"]
    fixed = design_space["fixed"]

    # Active search knobs must use one of the declared values.
    for knob, allowed_values in active.items():
        if knob not in candidate:
            raise HardwareConfigError(
                f"missing active hardware knob: {knob}"
            )

        if candidate[knob] not in allowed_values:
            raise HardwareConfigError(
                f"{knob}={candidate[knob]!r} is outside "
                f"allowed values {allowed_values!r}"
            )

    # Hardware-related fixed values must remain fixed.
    fixed_hardware_keys = {
        "cores",
        "l1i_cache_kib",
        "l1i_associativity",
        "l1i_latency_cycles",
        "l1d_latency_cycles",
        "l2_latency_cycles",
        "memory_type",
        "memory_size_mib",
        "simulation_mode",
    }

    for knob in fixed_hardware_keys:
        expected = fixed[knob]

        if knob not in candidate:
            raise HardwareConfigError(
                f"missing fixed hardware knob: {knob}"
            )

        if candidate[knob] != expected:
            raise HardwareConfigError(
                f"{knob} is fixed at {expected!r}, "
                f"got {candidate[knob]!r}"
            )

    # Cross-knob constraint from the design-space contract.
    if (
        candidate["cpu_model"] == "RiscvTimingSimpleCPU"
        and candidate["issue_width"] != 1
    ):
        raise HardwareConfigError(
            "RiscvTimingSimpleCPU requires issue_width=1"
        )


def build_baseline_candidate() -> dict[str, Any]:
    design_space = load_design_space()
    candidate = baseline_hardware_candidate(design_space)
    validate_hardware_candidate(candidate, design_space)
    return candidate
