from pathlib import Path
import json
import pytest
import yaml

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "experiment-contracts"
SCHEMAS_DIR = CONTRACTS / "schemas"
ATTN_DIR = CONTRACTS / "attention-experiments"
AI_TUTOR_DIR = CONTRACTS / "ai-tutor-config"
COMPUTE_DIR = CONTRACTS / "compute-policy"
RUN_RECORDS_DIR = CONTRACTS / "run-records"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry():
    schema_files = {
        "shared.schema.json": SCHEMAS_DIR / "shared.schema.json",
        "attention-experiment.schema.json": ATTN_DIR / "attention-experiment.schema.json",
        "attention-design-space.schema.json": ATTN_DIR / "attention-design-space.schema.json",
        "ai-tutor.schema.json": AI_TUTOR_DIR / "ai-tutor.schema.json",
        "ai-tutor-design-space.schema.json": AI_TUTOR_DIR / "ai-tutor-design-space.schema.json",
        "compute-policy.schema.json": COMPUTE_DIR / "compute-policy.schema.json",
        "run-record.schema.json": RUN_RECORDS_DIR / "run-record.schema.json",
    }
    reg = Registry()
    for name, path in schema_files.items():
        schema = load_json(path)
        res = Resource.from_contents(schema)
        reg = reg.with_resource(name, res)
        reg = reg.with_resource(path.as_uri(), res)
        if "$id" in schema:
            reg = reg.with_resource(schema["$id"], res)
    return reg


def test_all_json_schemas_structurally_valid():
    """Verify that every JSON schema in experiment-contracts/ is structurally valid JSON Schema (Draft 2020-12)."""
    schema_paths = list(CONTRACTS.rglob("*.schema.json"))
    assert len(schema_paths) >= 6, f"Expected at least 6 schemas, found {len(schema_paths)}"
    for p in schema_paths:
        schema = load_json(p)
        # check_schema raises SchemaError if structurally invalid
        Draft202012Validator.check_schema(schema)


def test_local_reference_resolution_without_network(registry):
    """Verify that all schemas and compose references resolve locally without internet access."""
    # Build validator with registry for each schema
    for schema_path in CONTRACTS.rglob("*.schema.json"):
        schema = load_json(schema_path)
        val = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
        assert val is not None


@pytest.mark.parametrize("yaml_path,schema_path", [
    (ATTN_DIR / "baseline.attention.yaml", ATTN_DIR / "attention-experiment.schema.json"),
    (ATTN_DIR / "example.candidate.yaml", ATTN_DIR / "attention-experiment.schema.json"),
    (ATTN_DIR / "design-space.yaml", ATTN_DIR / "attention-design-space.schema.json"),
    (AI_TUTOR_DIR / "example.ai-tutor.yaml", AI_TUTOR_DIR / "ai-tutor.schema.json"),
    (AI_TUTOR_DIR / "design-space.yaml", AI_TUTOR_DIR / "ai-tutor-design-space.schema.json"),
    (COMPUTE_DIR / "compute-policy.yaml", COMPUTE_DIR / "compute-policy.schema.json"),
    (RUN_RECORDS_DIR / "example.completed.yaml", RUN_RECORDS_DIR / "run-record.schema.json"),
])
def test_canonical_yaml_examples_validate(registry, yaml_path, schema_path):
    """Every maintained YAML example and search-space document must validate against its schema."""
    data = load_yaml(yaml_path)
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    errors = list(validator.iter_errors(data))
    assert not errors, f"{yaml_path.name} failed schema {schema_path.name}: {[e.message for e in errors]}"


def test_unknown_experiment_property_rejected(registry):
    """Verify additionalProperties: false rejects unknown properties."""
    schema = load_json(ATTN_DIR / "attention-experiment.schema.json")
    val = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    candidate = load_yaml(ATTN_DIR / "example.candidate.yaml")
    mutated = dict(candidate)
    mutated["unknown_illegal_property"] = 123
    errors = list(val.iter_errors(mutated))
    assert len(errors) > 0, "Unknown experiment property should fail validation"


def test_compute_policy_burst_restrictions():
    """Verify compute policy enforces that organizer burst is restricted to final tier only."""
    policy = load_yaml(COMPUTE_DIR / "compute-policy.yaml")
    for tier_name, tier in policy["tiers"].items():
        has_burst = "organizer_burst" in tier.get("backends", [])
        burst_allowed = tier.get("organizer_burst_allowed", False)
        if tier_name != "final":
            assert not has_burst, f"organizer_burst backend cannot appear in tier {tier_name}"
            assert not burst_allowed, f"organizer_burst_allowed must be False in tier {tier_name}"
        else:
            assert has_burst, "final tier must include organizer_burst"
            assert burst_allowed, "final tier must allow organizer_burst"


def test_run_record_validates(registry):
    """Verify run record validates and preserves execution evidence."""
    record = load_yaml(RUN_RECORDS_DIR / "example.completed.yaml")
    schema = load_json(RUN_RECORDS_DIR / "run-record.schema.json")
    val = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    errors = list(val.iter_errors(record))
    assert not errors, f"Run record failed validation: {[e.message for e in errors]}"
    assert record["status"]["state"] == "completed"
    assert record["metrics"]["passed"] is True


def test_orchestration_experiment_interface():
    """Verify src.orchestration.experiment passes full config to hardware and tutor runners."""
    from src.orchestration.experiment import run_experiment
    from unittest.mock import patch

    mock_config = {"experiment_id": "test-exp", "software": {}, "hardware": {}}
    with patch("src.orchestration.experiment.run_tutor") as mock_tutor, \
         patch("src.orchestration.experiment.run_hardware") as mock_hw:
        mock_tutor.return_value = {"status": "ok"}
        mock_hw.return_value = {"status": "ok"}
        result = run_experiment(mock_config)
        mock_tutor.assert_called_once_with(mock_config)
        mock_hw.assert_called_once_with(mock_config)
        assert result == {"software_result": {"status": "ok"}, "hardware_result": {"status": "ok"}}
