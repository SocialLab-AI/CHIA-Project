from pathlib import Path
import json
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "configs" / "schemas"
HARDWARE = ROOT / "configs" / "hardware"
SOFTWARE = ROOT / "configs" / "software"
EXAMPLES = ROOT / "configs" / "examples"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry():
    schema_files = {
        "chia-experiment.schema.json": load_json(SCHEMAS / "chia-experiment.schema.json"),
        "experiment.schema.json": load_json(SCHEMAS / "experiment.schema.json"),
        "design-space.schema.json": load_json(SCHEMAS / "design-space.schema.json"),
        "run-record.schema.json": load_json(SCHEMAS / "run-record.schema.json"),
    }
    reg = Registry()
    for name, schema in schema_files.items():
        res = Resource.from_contents(schema)
        reg = reg.with_resource(name, res)
        if "$id" in schema:
            reg = reg.with_resource(schema["$id"], res)
    return reg


def test_schema_files_structure():
    """Verify that configs/schemas contains only the 4 target schemas."""
    expected_schemas = {
        "chia-experiment.schema.json",
        "experiment.schema.json",
        "design-space.schema.json",
        "run-record.schema.json",
    }
    actual_schemas = {p.name for p in SCHEMAS.glob("*.json")}
    assert actual_schemas == expected_schemas, f"Unexpected schema files in {SCHEMAS}: {actual_schemas}"


def test_master_schema_defs_present():
    """Verify that chia-experiment.schema.json contains all required definitions."""
    master = load_json(SCHEMAS / "chia-experiment.schema.json")
    defs = master.get("$defs", {})
    required_defs = [
        "metadata",
        "workload",
        "software_config",
        "software_design_space",
        "hardware_config",
        "hardware_design_space",
        "application_metrics",
        "hardware_metrics",
        "objectives",
        "experiment",
        "design_space",
        "run_record",
    ]
    for d in required_defs:
        assert d in defs, f"Missing $defs entry: {d}"


def test_thin_schemas_reference_master(registry):
    """Verify that experiment, design-space, and run-record are thin schemas referencing master schema."""
    exp_schema = load_json(SCHEMAS / "experiment.schema.json")
    assert exp_schema.get("$ref") in (
        "chia-experiment.schema.json#/$defs/experiment",
        "https://example.local/chia/chia-experiment.schema.json#/$defs/experiment"
    )

    ds_schema = load_json(SCHEMAS / "design-space.schema.json")
    assert ds_schema.get("$ref") in (
        "chia-experiment.schema.json#/$defs/design_space",
        "https://example.local/chia/chia-experiment.schema.json#/$defs/design_space"
    )

    run_schema = load_json(SCHEMAS / "run-record.schema.json")
    assert run_schema.get("$ref") in (
        "chia-experiment.schema.json#/$defs/run_record",
        "https://example.local/chia/chia-experiment.schema.json#/$defs/run_record"
    )


def test_hardware_config_validation_through_master(registry):
    hw_val = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/hardware_config"},
        registry=registry,
        format_checker=FormatChecker()
    )
    baseline_hw = load_json(HARDWARE / "baseline.hardware.json")
    errors = list(hw_val.iter_errors(baseline_hw))
    assert not errors, f"Hardware config validation through master failed: {[e.message for e in errors]}"


def test_software_config_validation_through_master(registry):
    sw_val = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/software_config"},
        registry=registry,
        format_checker=FormatChecker()
    )
    baseline_sw = load_json(SOFTWARE / "baseline.software.json")
    errors = list(sw_val.iter_errors(baseline_sw))
    assert not errors, f"Software config validation through master failed: {[e.message for e in errors]}"


def test_hardware_design_space_through_master(registry):
    hw_ds_val = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/hardware_design_space"},
        registry=registry,
        format_checker=FormatChecker()
    )
    ds_hw = load_json(HARDWARE / "design-space.hardware.json")
    errors = list(hw_ds_val.iter_errors(ds_hw))
    assert not errors, f"Hardware design space validation failed: {[e.message for e in errors]}"
    assert len(ds_hw["active_knobs"]) == 8


def test_software_design_space_through_master(registry):
    sw_ds_val = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/software_design_space"},
        registry=registry,
        format_checker=FormatChecker()
    )
    ds_sw = load_json(SOFTWARE / "design-space.software.json")
    errors = list(sw_ds_val.iter_errors(ds_sw))
    assert not errors, f"Software design space validation failed: {[e.message for e in errors]}"
    assert len(ds_sw["active_knobs"]) == 4


def test_combined_design_space_schema(registry):
    ds_val = Draft202012Validator(
        load_json(SCHEMAS / "design-space.schema.json"),
        registry=registry,
        format_checker=FormatChecker()
    )
    combined = {
        "schema_version": "1.0",
        "software": load_json(SOFTWARE / "design-space.software.json"),
        "hardware": load_json(HARDWARE / "design-space.hardware.json"),
    }
    errors = list(ds_val.iter_errors(combined))
    assert not errors, f"Combined design space validation failed: {[e.message for e in errors]}"


def test_quality_and_latency_are_not_knobs():
    ds_sw = load_json(SOFTWARE / "design-space.software.json")
    active_knobs = ds_sw["active_knobs"]
    assert "answer_quality" not in active_knobs
    assert "latency_ms" not in active_knobs
    assert "quality" not in active_knobs
    assert "latency" not in active_knobs

    opt_metrics = ds_sw["optimization_metrics"]
    assert opt_metrics["answer_quality"]["direction"] == "maximize"
    assert opt_metrics["latency_ms"]["direction"] == "minimize"


def test_metrics_separation_in_master():
    master = load_json(SCHEMAS / "chia-experiment.schema.json")
    app_metrics = master["$defs"]["application_metrics"]["properties"]
    hw_metrics = master["$defs"]["hardware_metrics"]["properties"]

    assert "answer_quality" in app_metrics
    assert "latency_ms" in app_metrics
    assert "cycles" in hw_metrics or "execution_cycles" in hw_metrics
    assert "ipc" in hw_metrics
    assert "sim_ticks" in hw_metrics


def test_unknown_experiment_property_fails(registry):
    exp_val = Draft202012Validator(
        load_json(SCHEMAS / "experiment.schema.json"),
        registry=registry,
        format_checker=FormatChecker()
    )
    baseline = load_json(EXAMPLES / "baseline.json")
    mutated = dict(baseline)
    mutated["unknown_illegal_property"] = 123
    errors = list(exp_val.iter_errors(mutated))
    assert len(errors) > 0, "Unknown experiment property should fail validation"


def test_run_record_schema_validates(registry):
    run_val = Draft202012Validator(
        load_json(SCHEMAS / "run-record.schema.json"),
        registry=registry,
        format_checker=FormatChecker()
    )
    record = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "experiment_id": "baseline",
        "status": "success",
        "started_at": "2026-09-11T12:00:00Z",
        "finished_at": "2026-09-11T12:05:00Z",
        "config_snapshot": load_json(EXAMPLES / "baseline.json"),
        "metrics": {
            "application": {
                "answer_quality": 0.85,
                "latency_ms": 120.5
            },
            "hardware": {
                "cycles": 1500000,
                "ipc": 1.45,
                "sim_ticks": 750000000
            }
        }
    }
    errors = list(run_val.iter_errors(record))
    assert not errors, f"Run record validation failed: {[e.message for e in errors]}"
