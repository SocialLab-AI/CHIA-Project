from pathlib import Path
import json

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "configs" / "schemas"
HARDWARE = ROOT / "configs" / "hardware"
SOFTWARE = ROOT / "configs" / "software"
EXAMPLES = ROOT / "configs" / "examples"

ILLEGAL_HW_CASES = [
    ("cores", 3),
    ("l1d_cache_kib", 128),
    ("l2_associativity", 2),
    ("cpu_model", "SomeOtherCPU"),
    ("isa", "X86"),
    ("memory_type", "DDR4"),
    ("simulation_mode", "FS"),
    ("software_threads", 4),
]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_validators():
    schema_files = {
        "chia-experiment.schema.json": load(SCHEMAS / "chia-experiment.schema.json"),
        "experiment.schema.json": load(SCHEMAS / "experiment.schema.json"),
        "design-space.schema.json": load(SCHEMAS / "design-space.schema.json"),
        "run-record.schema.json": load(SCHEMAS / "run-record.schema.json"),
    }

    registry = Registry()
    for name, schema in schema_files.items():
        res = Resource.from_contents(schema)
        registry = registry.with_resource(name, res)
        if "$id" in schema:
            registry = registry.with_resource(schema["$id"], res)

    hw_validator = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/hardware_config"},
        registry=registry,
        format_checker=FormatChecker(),
    )
    hw_ds_validator = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/hardware_design_space"},
        registry=registry,
        format_checker=FormatChecker(),
    )
    sw_validator = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/software_config"},
        registry=registry,
        format_checker=FormatChecker(),
    )
    sw_ds_validator = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/software_design_space"},
        registry=registry,
        format_checker=FormatChecker(),
    )
    exp_validator = Draft202012Validator(
        schema_files["experiment.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )
    ds_validator = Draft202012Validator(
        schema_files["design-space.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )
    run_record_validator = Draft202012Validator(
        schema_files["run-record.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )

    return hw_validator, hw_ds_validator, sw_validator, sw_ds_validator, exp_validator, ds_validator, run_record_validator


def validate_file(validator, file_path: Path) -> bool:
    instance = load(file_path)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        print(f"[FAIL] {file_path.relative_to(ROOT)}")
        for error in errors:
            location = ".".join(str(x) for x in error.path) or "<root>"
            print(f"  {location}: {error.message}")
        return False
    print(f"[OK]   {file_path.relative_to(ROOT)}")
    return True


def test_illegal_hardware_values(hw_validator) -> bool:
    baseline = load(HARDWARE / "baseline.hardware.json")
    all_passed = True
    for field, illegal_val in ILLEGAL_HW_CASES:
        candidate = dict(baseline)
        candidate[field] = illegal_val
        errors = list(hw_validator.iter_errors(candidate))
        if not errors:
            print(f"[FAIL] Illegal hardware value accepted: {field}={illegal_val}")
            all_passed = False
        else:
            print(f"[OK]   Illegal hardware value rejected as expected: {field}={illegal_val}")
    return all_passed


def test_software_negative_cases(sw_ds_validator) -> bool:
    ds = load(SOFTWARE / "design-space.software.json")
    all_passed = True

    # 1. Attempting to add quality/latency as active knobs (must be rejected)
    for bad_knob in ["answer_quality", "latency_ms", "quality", "latency"]:
        mutated = json.loads(json.dumps(ds))
        mutated["active_knobs"][bad_knob] = {"status": "pending_definition"}
        errors = list(sw_ds_validator.iter_errors(mutated))
        if not errors:
            print(f"[FAIL] Metric '{bad_knob}' improperly accepted as active software knob")
            all_passed = False
        else:
            print(f"[OK]   Metric '{bad_knob}' rejected as active software knob as expected")

    # 2. Attempting non-ollama runtime
    mutated = json.loads(json.dumps(ds))
    mutated["fixed_parameters"]["runtime"] = "vllm"
    errors = list(sw_ds_validator.iter_errors(mutated))
    if not errors:
        print("[FAIL] Illegal runtime accepted in fixed parameters")
        all_passed = False
    else:
        print("[OK]   Non-ollama runtime rejected as expected")

    # 3. Attempting non-1B parameter count
    mutated = json.loads(json.dumps(ds))
    mutated["fixed_parameters"]["parameter_count"] = "8B"
    errors = list(sw_ds_validator.iter_errors(mutated))
    if not errors:
        print("[FAIL] Illegal parameter count accepted in fixed parameters")
        all_passed = False
    else:
        print("[OK]   Non-1B parameter count rejected as expected")

    return all_passed


def inspect_software_baseline(sw_validator) -> bool:
    baseline_path = SOFTWARE / "baseline.software.json"
    baseline = load(baseline_path)
    errors = list(sw_validator.iter_errors(baseline))
    if errors:
        print(f"[FAIL] {baseline_path.relative_to(ROOT)} failed schema validation")
        for e in errors:
            print(f"  {e.message}")
        return False

    is_runtime_ready = baseline.get("runtime_ready", False)
    if not is_runtime_ready:
        unresolved = baseline.get("unresolved_fields", [])
        print(f"[OK]   {baseline_path.relative_to(ROOT)} validated as DRAFT software configuration")
        print(f"[INFO] Software baseline runtime_ready=False. Unresolved fields ({len(unresolved)}):")
        for field in unresolved:
            print(f"       - {field}")
    else:
        print(f"[OK]   {baseline_path.relative_to(ROOT)} validated as EXECUTION-READY software configuration")
    return True


def main():
    hw_validator, hw_ds_validator, sw_validator, sw_ds_validator, exp_validator, ds_validator, _ = build_validators()
    failed = False

    # 1. Validate baseline hardware configuration against chia-experiment.schema.json#/$defs/hardware_config
    if not validate_file(hw_validator, HARDWARE / "baseline.hardware.json"):
        failed = True

    # 2. Validate hardware design space configuration against chia-experiment.schema.json#/$defs/hardware_design_space
    if not validate_file(hw_ds_validator, HARDWARE / "design-space.hardware.json"):
        failed = True

    # 3. Validate software design space configuration against chia-experiment.schema.json#/$defs/software_design_space
    if not validate_file(sw_ds_validator, SOFTWARE / "design-space.software.json"):
        failed = True

    # 4. Inspect/validate software baseline against chia-experiment.schema.json#/$defs/software_config
    if not inspect_software_baseline(sw_validator):
        failed = True

    # 5. Validate experiment examples against configs/schemas/experiment.schema.json
    for example_path in sorted(EXAMPLES.glob("*.json")):
        if not validate_file(exp_validator, example_path):
            failed = True

    # 6. Verify negative test cases for illegal hardware values
    if not test_illegal_hardware_values(hw_validator):
        failed = True

    # 7. Verify negative test cases for software design space
    if not test_software_negative_cases(sw_ds_validator):
        failed = True

    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
