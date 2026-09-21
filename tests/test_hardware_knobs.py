import pytest

from src.hardware.knobs import (
    HardwareConfigError,
    build_baseline_candidate,
    load_design_space,
    validate_hardware_candidate,
)


def test_baseline_candidate_is_valid():
    candidate = build_baseline_candidate()

    assert candidate["cpu_model"] == "RiscvO3CPU"
    assert candidate["frequency_ghz"] == 1
    assert candidate["issue_width"] == 2
    assert candidate["l1d_cache_kib"] == 64
    assert candidate["l2_cache_kib"] == 1024


def test_rejects_value_outside_design_space():
    design_space = load_design_space()
    candidate = build_baseline_candidate()

    candidate["frequency_ghz"] = 99

    with pytest.raises(HardwareConfigError):
        validate_hardware_candidate(candidate, design_space)


def test_timing_simple_requires_issue_width_one():
    design_space = load_design_space()
    candidate = build_baseline_candidate()

    candidate["cpu_model"] = "RiscvTimingSimpleCPU"
    candidate["issue_width"] = 2

    with pytest.raises(HardwareConfigError):
        validate_hardware_candidate(candidate, design_space)


def test_valid_timing_simple_candidate():
    design_space = load_design_space()
    candidate = build_baseline_candidate()

    candidate["cpu_model"] = "RiscvTimingSimpleCPU"
    candidate["issue_width"] = 1

    validate_hardware_candidate(candidate, design_space)
