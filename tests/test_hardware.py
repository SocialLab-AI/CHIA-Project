from pathlib import Path
import json
import time
from unittest.mock import patch
import pytest
import yaml

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "experiment-contracts"
SCHEMAS_DIR = CONTRACTS / "schemas"
BASELINES_DIR = CONTRACTS / "baselines"
DESIGN_SPACES_DIR = CONTRACTS / "design-spaces"
EXAMPLES_DIR = CONTRACTS / "examples"

MASTER_SCHEMA_PATH = SCHEMAS_DIR / "chia-experiment.schema.yaml"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def master_schema():
    assert MASTER_SCHEMA_PATH.exists(), f"Missing master schema: {MASTER_SCHEMA_PATH}"
    schema = load_yaml(MASTER_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return schema


def get_validator(master_schema: dict, def_name: str) -> Draft202012Validator:
    subschema = {
        "$schema": master_schema.get(
            "$schema", "https://json-schema.org/draft/2020-12/schema"
        ),
        "$ref": f"#/$defs/{def_name}",
        "$defs": master_schema.get("$defs", {}),
    }
    return Draft202012Validator(subschema, format_checker=FormatChecker())


@pytest.fixture(scope="module")
def hw_validator(master_schema):
    return get_validator(master_schema, "attention_experiment")


@pytest.fixture(scope="module")
def hw_ds_validator(master_schema):
    return get_validator(master_schema, "hardware_design_space")


def test_baseline_attention_valid(hw_validator):
    baseline = load_yaml(BASELINES_DIR / "attention.yaml")
    errors = list(hw_validator.iter_errors(baseline))
    assert not errors, (
        f"Baseline attention validation errors: {[e.message for e in errors]}"
    )


def test_q4_campaign_restrictions():
    """Preserve current main's Q4 campaign restrictions."""
    baseline = load_yaml(BASELINES_DIR / "attention.yaml")
    hw = baseline["hardware"]
    sw = baseline["software"]
    meas = baseline["measurement"]
    workload = baseline["workload"]

    assert hw["cores"] == 2
    assert sw["threads"] == 2
    assert sw["kv_format"] == "Q4"
    assert workload["layers"] == 1
    assert meas["repetitions"] == 10
    assert meas["warmup_runs"] == 0
    assert hw["memory_type"] == "DDR3_1600_8x8"
    assert hw["memory_size_mib"] == 16
    assert hw["simulation_mode"] == "SE"
    assert baseline["status"]["state"] == "planned"


def test_timing_simple_cpu_issue_width_constraint(hw_validator):
    """TimingSimpleCPU requires issue_width == 1; issue_width == 2 must be rejected."""
    candidate = load_yaml(EXAMPLES_DIR / "attention-candidate.yaml")
    valid_timing = dict(candidate)
    valid_timing["hardware"]["cpu_model"] = "RiscvTimingSimpleCPU"
    valid_timing["hardware"]["issue_width"] = 1
    errors = list(hw_validator.iter_errors(valid_timing))
    assert not errors, (
        f"Expected issue_width=1 for TimingSimpleCPU to pass, got: {errors}"
    )

    invalid_timing = json.loads(json.dumps(candidate))
    invalid_timing["hardware"]["cpu_model"] = "RiscvTimingSimpleCPU"
    invalid_timing["hardware"]["issue_width"] = 2
    errors = list(hw_validator.iter_errors(invalid_timing))
    assert len(errors) > 0, "Expected issue_width=2 for TimingSimpleCPU to be rejected"


@pytest.mark.parametrize(
    "field,illegal_val",
    [
        ("cores", 3),
        ("l1d_cache_kib", 128),
        ("l2_associativity", 2),
        ("cpu_model", "InvalidCPU"),
        ("frequency_ghz", 5),
        ("memory_type", "DDR4"),
        ("memory_size_mib", 32),
        ("simulation_mode", "FS"),
    ],
)
def test_illegal_hardware_values_rejected(hw_validator, field, illegal_val):
    candidate = load_yaml(EXAMPLES_DIR / "attention-candidate.yaml")
    mutated = json.loads(json.dumps(candidate))
    mutated["hardware"][field] = illegal_val
    errors = list(hw_validator.iter_errors(mutated))
    assert len(errors) > 0, f"Expected {field}={illegal_val} to be rejected"


def test_active_hardware_knobs(hw_ds_validator):
    """Verify the 7 active hardware search knobs in Q4 design space."""
    ds = load_yaml(DESIGN_SPACES_DIR / "hardware.yaml")
    errors = list(hw_ds_validator.iter_errors(ds))
    assert not errors, f"Design space validation failed: {[e.message for e in errors]}"

    active_hw = ds["active_candidates"]["hardware"]
    expected_knobs = {
        "cpu_model",
        "frequency_ghz",
        "issue_width",
        "l1d_cache_kib",
        "l1d_associativity",
        "l2_cache_kib",
        "l2_associativity",
    }
    assert set(active_hw.keys()) == expected_knobs
    assert ds["fixed"]["cores"] == 2
    assert ds["fixed"]["kv_format"] == "Q4"


def test_production_profile_does_not_reuse_calibration_metrics():
    """The selected profile must not claim measurements before its smoke."""
    baseline = load_yaml(BASELINES_DIR / "attention.yaml")
    metrics = baseline["metrics"]

    assert all(value is None for value in metrics.values())


def test_hardware_runner_rejects_invalid_candidate():
    """Invalid candidates must fail before runtime access."""
    from src.hardware.runner import run_hardware

    with pytest.raises(ValueError):
        run_hardware({})


def test_hardware_runner_executes_energy_inside_shared_deadline():
    from src.common.candidate import Candidate, baseline_candidate
    from src.common.security import digest
    from src.hardware.energy_mapping import ENERGY_SCOPE
    from src.hardware.runner import run_gem5_candidate

    config = baseline_candidate()
    candidate_id = Candidate.from_dict(config).candidate_id
    gem5_result = {
        "candidate_id": candidate_id,
        "status": "completed",
        "hardware": config["hardware"],
        "workload": config["workload"],
        "metrics": {"simulated_seconds": 1.0},
        "correctness": {"status": "PASS"},
        "provenance": {"stats_sha256": "a" * 64},
        "artifacts": {"directory": "/tmp/gem5/run-a", "stats": "stats.txt"},
    }
    gem5_result_id = digest(gem5_result)
    energy_result = {
        "candidate_id": candidate_id,
        "status": "completed",
        "hardware_result_id": gem5_result_id,
        "stats_sha256": "a" * 64,
        "metrics": {"estimated_cache_dynamic_energy_uj": 4.5},
        "scope": ENERGY_SCOPE,
        "provenance": {"estimator": "fixture"},
    }
    runtime = {
        "timeout_seconds": 10,
        "correctness_tolerance": {
            "max_absolute_error": 0.1,
            "mean_squared_error": 0.01,
        },
        "artifacts_root": "/tmp/gem5",
        "energy": {
            "image": "chia-energy-tools:0.3",
            "timeout_seconds": 300,
            "artifacts_root": "/tmp/energy",
        },
        "deadline_epoch_seconds": time.time() + 10,
    }
    preflight = {"docker": "docker", "image": "chia-energy-tools:0.3"}
    # Imports occur inside the runner, so patch the defining estimator module.
    with patch(
        "src.hardware.energy_estimator.preflight_energy_runtime",
        return_value=preflight,
    ) as energy_preflight, patch(
        "src.hardware.runner._run_gem5_only",
        return_value=gem5_result,
    ) as gem5, patch(
        "src.hardware.energy_estimator.run_energy_candidate",
        return_value=energy_result,
    ) as energy:
        result = run_gem5_candidate(config, runtime, {"run_id": "run-a"})

    assert gem5.call_count == 1 and energy.call_count == 1
    assert energy_preflight.call_count == 1
    energy_runtime = energy.call_args.args[2]
    assert 0 < energy_runtime["timeout_seconds"] <= 10
    assert energy_runtime["deadline_epoch_seconds"] <= runtime[
        "deadline_epoch_seconds"
    ]
    assert energy_runtime["hardware_artifacts_root"] == "/tmp/gem5"
    assert result["metrics"]["energy_uj"] == 4.5
    assert result["metrics"]["energy_scope"] == ENERGY_SCOPE
    assert result["energy_evidence"] == energy_result
