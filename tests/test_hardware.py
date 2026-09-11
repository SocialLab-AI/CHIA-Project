from pathlib import Path
import json
import pytest

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "configs" / "schemas"
HARDWARE = ROOT / "configs" / "hardware"
EXAMPLES = ROOT / "configs" / "examples"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml_simple(path: Path):
    """Simple parser for simple YAML files without requiring PyYAML."""
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if v.isdigit():
                data[k] = int(v)
            elif (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                data[k] = v[1:-1]
            elif v in ("true", "True"):
                data[k] = True
            elif v in ("false", "False"):
                data[k] = False
            elif v == "":
                continue
            else:
                data[k] = v
    return data


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


@pytest.fixture(scope="module")
def hw_validator(registry):
    return Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/hardware_config"},
        registry=registry,
        format_checker=FormatChecker()
    )


@pytest.fixture(scope="module")
def hw_ds_validator(registry):
    return Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/hardware_design_space"},
        registry=registry,
        format_checker=FormatChecker()
    )


@pytest.fixture(scope="module")
def exp_validator(registry):
    schema = load_json(SCHEMAS / "experiment.schema.json")
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def test_baseline_hardware_valid(hw_validator):
    baseline = load_json(HARDWARE / "baseline.hardware.json")
    errors = list(hw_validator.iter_errors(baseline))
    assert not errors, f"Baseline hardware validation errors: {[e.message for e in errors]}"


def test_baseline_hardware_yaml_matches_json():
    json_baseline = load_json(HARDWARE / "baseline.hardware.json")
    try:
        import yaml
        yaml_baseline = yaml.safe_load((HARDWARE / "baseline.hardware.yaml").read_text(encoding="utf-8"))
    except ImportError:
        yaml_baseline = load_yaml_simple(HARDWARE / "baseline.hardware.yaml")
    assert json_baseline == yaml_baseline


def test_design_space_hardware_valid(hw_ds_validator):
    ds = load_json(HARDWARE / "design-space.hardware.json")
    errors = list(hw_ds_validator.iter_errors(ds))
    assert not errors, f"Design space hardware validation errors: {[e.message for e in errors]}"


def test_official_active_knobs_count_and_members(hw_ds_validator):
    ds = load_json(HARDWARE / "design-space.hardware.json")
    active_knobs = ds["active_knobs"]
    assert len(active_knobs) == 8, f"Expected exactly 8 active hardware knobs, got {len(active_knobs)}"
    expected_knobs = {
        "cpu_model", "cores", "frequency_ghz", "issue_width",
        "l1d_cache_kib", "l1d_associativity", "l2_cache_kib", "l2_associativity"
    }
    assert set(active_knobs.keys()) == expected_knobs


def test_official_fixed_parameters(hw_ds_validator):
    ds = load_json(HARDWARE / "design-space.hardware.json")
    fixed = ds["fixed_parameters"]
    assert fixed["isa"] == "RISCV64"
    assert fixed["l1i_cache_kib"] == 16
    assert fixed["l1i_associativity"] == 2
    assert fixed["l1i_latency_cycles"] == 2
    assert fixed["l1d_latency_cycles"] == 2
    assert fixed["l2_latency_cycles"] == 20
    assert fixed["memory_type"] == "DDR3_1600_8x8"
    assert fixed["memory_size_mib"] == 16
    assert fixed["simulation_mode"] == "SE"
    assert fixed["software_threads"] == 2


def test_examples_valid(exp_validator):
    for example_file in sorted(EXAMPLES.glob("*.json")):
        example_data = load_json(example_file)
        errors = list(exp_validator.iter_errors(example_data))
        assert not errors, f"{example_file.name} failed validation: {[e.message for e in errors]}"


@pytest.mark.parametrize("field,illegal_val", [
    ("cores", 3),
    ("l1d_cache_kib", 128),
    ("l2_associativity", 2),
    ("cpu_model", "SomeOtherCPU"),
    ("isa", "X86"),
    ("memory_type", "DDR4"),
    ("simulation_mode", "FS"),
    ("software_threads", 4),
])
def test_illegal_hardware_values_rejected(hw_validator, field, illegal_val):
    baseline = load_json(HARDWARE / "baseline.hardware.json")
    candidate = dict(baseline)
    candidate[field] = illegal_val
    errors = list(hw_validator.iter_errors(candidate))
    assert len(errors) > 0, f"Expected {field}={illegal_val} to be rejected"


def test_issue_width_conditional_metadata(hw_ds_validator):
    ds = load_json(HARDWARE / "design-space.hardware.json")
    iw = ds["active_knobs"]["issue_width"]
    assert iw["values"] == [1, 2, 4]
    assert iw["baseline"] == 2
    assert iw["applicability"] == "RiscvO3CPU"
    assert iw["implementation_status"] == "pending_validation"


def test_timing_simple_cpu_issue_width_constraint(hw_validator):
    baseline = load_json(HARDWARE / "baseline.hardware.json")
    # TimingSimpleCPU with issue_width=1 should pass
    valid_simple = dict(baseline)
    valid_simple["cpu_model"] = "RiscvTimingSimpleCPU"
    valid_simple["issue_width"] = 1
    errors = list(hw_validator.iter_errors(valid_simple))
    assert not errors, f"Expected issue_width=1 for TimingSimpleCPU to pass, got: {errors}"

    # TimingSimpleCPU with issue_width=2 should be rejected
    invalid_simple = dict(baseline)
    invalid_simple["cpu_model"] = "RiscvTimingSimpleCPU"
    invalid_simple["issue_width"] = 2
    errors = list(hw_validator.iter_errors(invalid_simple))
    assert len(errors) > 0, "Expected issue_width=2 for TimingSimpleCPU to be rejected"

