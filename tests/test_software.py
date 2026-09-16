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
DOCS_DIR = ROOT / "docs"

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
def sw_ds_validator(master_schema):
    return get_validator(master_schema, "software_design_space")


def test_software_design_space_valid(sw_ds_validator):
    ds = load_yaml(DESIGN_SPACES_DIR / "software.yaml")
    errors = list(sw_ds_validator.iter_errors(ds))
    assert not errors, (
        f"design-spaces/software.yaml failed validation: {[e.message for e in errors]}"
    )


def test_software_search_is_bounded_and_artifact_is_fixed():
    """Only sampling/output knobs are active; model identity remains fixed."""
    ds = load_yaml(DESIGN_SPACES_DIR / "software.yaml")
    assert ds["active_candidates"] == {
        "temperature": [0.0, 0.2, 0.5],
        "max_output_tokens": [128, 256, 384],
    }
    assert ds["pending_search_space"]["status"] == "resolved_for_integration"
    assert len(ds["pending_search_space"]["knobs"]) == 2

    # Optimization metrics
    metrics = ds["optimization_metrics"]
    assert metrics["answer_quality"]["direction"] == "maximize"
    assert metrics["latency_ms"]["direction"] == "minimize"


def test_removed_retrieval_knob_is_rejected(master_schema):
    """Reject retired software fields instead of silently ignoring them."""
    val = get_validator(master_schema, "tutor_config")
    data = load_yaml(BASELINES_DIR / "tutor.yaml")

    bad_data = json.loads(json.dumps(data))
    bad_data["software"]["chunk_unit"] = "tokens"
    errors = list(val.iter_errors(bad_data))
    assert len(errors) > 0, "Schema should reject the removed field"


def test_manifest_consistency():
    """Verify that docs/knob-mapping.manifest.json is consistent with active fields and statuses."""
    manifest = load_json(DOCS_DIR / "knob-mapping.manifest.json")
    fields = manifest["fields"]
    assert len(fields) >= 20

    field_map = {f["field"]: f for f in fields}
    assert "software.model" in field_map
    assert field_map["software.model"]["baseline"] == "Qwen2.5 0.5B Instruct"
    assert field_map["software.quantization"]["baseline"] == "Q5_K_M"
    assert field_map["software.cpu_threads"]["baseline"] == 4
    assert field_map["software.runtime_ready"]["baseline"] is True


def test_no_stale_active_configs_references():
    """Verify that no active configuration or test code references the deleted legacy config directory or superseded contract paths."""
    legacy_dirs = [
        "configs",
        "ai-tutor-config",
        "attention-experiments",
        "compute-policy",
        "run-records",
    ]

    for py_file in ROOT.glob("scripts/*.py"):
        text = py_file.read_text(encoding="utf-8")
        for d in legacy_dirs:
            legacy_ref = f"{d}/"
            assert (
                legacy_ref not in text and f'{d}"' not in text and f"{d}'" not in text
            ), f"Stale {d} reference in {py_file}"

    for py_file in ROOT.glob("tests/*.py"):
        if py_file.name == "test_software.py":
            continue
        text = py_file.read_text(encoding="utf-8")
        for d in legacy_dirs:
            legacy_ref = f"{d}/"
            assert (
                legacy_ref not in text and f'{d}"' not in text and f"{d}'" not in text
            ), f"Stale {d} reference in {py_file}"
