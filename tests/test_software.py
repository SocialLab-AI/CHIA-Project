from pathlib import Path
import json
import pytest
import yaml

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "experiment-contracts"
AI_TUTOR_DIR = CONTRACTS / "ai-tutor-config"
SCHEMAS_DIR = CONTRACTS / "schemas"
DOCS_DIR = ROOT / "docs"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry():
    schema_files = {
        "shared.schema.json": SCHEMAS_DIR / "shared.schema.json",
        "ai-tutor.schema.json": AI_TUTOR_DIR / "ai-tutor.schema.json",
        "ai-tutor-design-space.schema.json": AI_TUTOR_DIR / "ai-tutor-design-space.schema.json",
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


@pytest.fixture(scope="module")
def sw_ds_validator(registry):
    schema = load_json(AI_TUTOR_DIR / "ai-tutor-design-space.schema.json")
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def test_software_design_space_valid(sw_ds_validator):
    ds = load_yaml(AI_TUTOR_DIR / "design-space.yaml")
    errors = list(sw_ds_validator.iter_errors(ds))
    assert not errors, f"design-space.yaml failed validation: {[e.message for e in errors]}"


def test_software_search_recorded_as_pending():
    """Verify that software search is explicitly recorded as pending and active_candidates is empty."""
    ds = load_yaml(AI_TUTOR_DIR / "design-space.yaml")
    assert ds["active_candidates"] == {}
    assert ds["pending_search_space"]["status"] == "pending_definition"
    assert len(ds["pending_search_space"]["knobs"]) == 4

    # Optimization metrics
    metrics = ds["optimization_metrics"]
    assert metrics["answer_quality"]["direction"] == "maximize"
    assert metrics["latency_ms"]["direction"] == "minimize"


def test_negative_invalid_chunk_unit(registry):
    """Reject chunk units other than characters."""
    schema = load_json(AI_TUTOR_DIR / "ai-tutor.schema.json")
    val = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")

    bad_data = json.loads(json.dumps(data))
    bad_data["software"]["chunk_unit"] = "tokens"
    errors = list(val.iter_errors(bad_data))
    assert len(errors) > 0, "Schema should reject chunk_unit != 'characters'"


def test_manifest_consistency():
    """Verify that docs/knob-mapping.manifest.json is consistent with active fields and statuses."""
    manifest = load_json(DOCS_DIR / "knob-mapping.manifest.json")
    fields = manifest["fields"]
    assert len(fields) >= 20

    field_map = {f["field"]: f for f in fields}
    assert "software.model" in field_map
    assert field_map["software.model"]["baseline"] == "Llama 3.2 1B Instruct"
    assert field_map["software.quantization"]["baseline"] == "Q4_K_M"
    assert field_map["software.chunk_size"]["unit"] == "characters"
    assert field_map["software.chunk_overlap"]["unit"] == "characters"
    assert field_map["software.cpu_threads"]["baseline"] == 4
    assert field_map["software.runtime_ready"]["baseline"] is False


def test_no_stale_active_configs_references():
    """Verify that no active configuration or test code references the deleted legacy config directory."""
    legacy_dir_name = "configs"
    legacy_ref = f"{legacy_dir_name}/"
    for py_file in ROOT.glob("scripts/*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert legacy_ref not in text and f'{legacy_dir_name}"' not in text and f"{legacy_dir_name}'" not in text, f"Stale configs reference in {py_file}"

    for py_file in ROOT.glob("tests/*.py"):
        if py_file.name == "test_software.py":
            continue
        text = py_file.read_text(encoding="utf-8")
        assert legacy_ref not in text and f'{legacy_dir_name}"' not in text and f"{legacy_dir_name}'" not in text, f"Stale configs reference in {py_file}"
