from pathlib import Path
import json
import pytest
import yaml

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "experiment-contracts"
SCHEMAS_DIR = CONTRACTS / "schemas"
BASELINES_DIR = CONTRACTS / "baselines"
DESIGN_SPACES_DIR = CONTRACTS / "design-spaces"
POLICIES_DIR = CONTRACTS / "policies"
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


def test_master_schema_structurally_valid(master_schema):
    """Verify that the master YAML schema is a structurally valid JSON Schema Draft 2020-12 document."""
    Draft202012Validator.check_schema(master_schema)
    assert master_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_master_schema_owns_authoritative_definitions(master_schema):
    """Verify $defs owns authoritative definitions for all required domain concepts."""
    defs = master_schema.get("$defs", {})
    required_defs = [
        "experiment_config",
        "tutor_config",
        "attention_experiment",
        "hardware",
        "software",
        "workload",
        "metrics",
        "objectives",
        "design_spaces",
        "compute_policy",
        "run_record",
    ]
    for d in required_defs:
        assert d in defs, f"Master schema $defs missing required definition: {d}"


def test_local_reference_resolution_without_network(master_schema):
    """Verify all internal references in the master schema resolve locally without internet access."""
    for def_name in master_schema["$defs"].keys():
        val = get_validator(master_schema, def_name)
        assert val is not None


@pytest.mark.parametrize(
    "yaml_path,def_name",
    [
        (BASELINES_DIR / "tutor.yaml", "tutor_config"),
        (BASELINES_DIR / "attention.yaml", "attention_experiment"),
        (DESIGN_SPACES_DIR / "software.yaml", "software_design_space"),
        (DESIGN_SPACES_DIR / "hardware.yaml", "hardware_design_space"),
        (POLICIES_DIR / "compute-policy.yaml", "compute_policy"),
        (EXAMPLES_DIR / "attention-candidate.yaml", "attention_experiment"),
        (EXAMPLES_DIR / "completed-run.yaml", "run_record"),
    ],
)
def test_canonical_yaml_examples_validate(master_schema, yaml_path, def_name):
    """Every maintained YAML example and search-space document must validate against its master schema definition."""
    data = load_yaml(yaml_path)
    val = get_validator(master_schema, def_name)
    errors = list(val.iter_errors(data))
    assert not errors, (
        f"{yaml_path.name} failed #/$defs/{def_name}: {[e.message for e in errors]}"
    )


def test_unknown_experiment_property_rejected(master_schema):
    """Verify additionalProperties: false rejects unknown properties."""
    val = get_validator(master_schema, "attention_experiment")
    candidate = load_yaml(EXAMPLES_DIR / "attention-candidate.yaml")
    mutated = dict(candidate)
    mutated["unknown_illegal_property"] = 123
    errors = list(val.iter_errors(mutated))
    assert len(errors) > 0, "Unknown experiment property should fail validation"


def test_compute_policy_burst_restrictions():
    """Verify compute policy enforces that organizer burst is restricted to final tier only."""
    policy = load_yaml(POLICIES_DIR / "compute-policy.yaml")
    for tier_name, tier in policy["tiers"].items():
        has_burst = "organizer_burst" in tier.get("backends", [])
        burst_allowed = tier.get("organizer_burst_allowed", False)
        if tier_name != "final":
            assert not has_burst, (
                f"organizer_burst backend cannot appear in tier {tier_name}"
            )
            assert not burst_allowed, (
                f"organizer_burst_allowed must be False in tier {tier_name}"
            )
        else:
            assert has_burst, "final tier must include organizer_burst"
            assert burst_allowed, "final tier must allow organizer_burst"


def test_run_record_validates(master_schema):
    """Verify run record validates and preserves execution evidence."""
    record = load_yaml(EXAMPLES_DIR / "completed-run.yaml")
    val = get_validator(master_schema, "run_record")
    errors = list(val.iter_errors(record))
    assert not errors, f"Run record failed validation: {[e.message for e in errors]}"
    assert record["status"]["state"] == "completed"
    assert record["metrics"]["passed"] is True


def test_orchestration_experiment_interface(tmp_path):
    """The canonical executor records invalid inputs without invoking runtime nodes."""
    from src.orchestration.experiment import run_experiment
    from unittest.mock import patch

    with patch("src.orchestration.experiment.LocalDispatcher") as dispatch:
        result = run_experiment({}, results_root=tmp_path)
        assert result["status"] == "rejected"
        dispatch.return_value.submit.assert_not_called()
