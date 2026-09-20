from pathlib import Path
import json
import pytest
import yaml

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "experiment-contracts"
SCHEMAS_DIR = CONTRACTS / "schemas"
BASELINES_DIR = CONTRACTS / "baselines"

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
def tutor_validator(master_schema):
    return get_validator(master_schema, "tutor_config")


def test_tutor_example_validates(tutor_validator):
    tutor_data = load_yaml(BASELINES_DIR / "tutor.yaml")
    errors = list(tutor_validator.iter_errors(tutor_data))
    assert not errors, (
        f"baselines/tutor.yaml failed validation: {[e.message for e in errors]}"
    )


def test_verified_software_baseline_values():
    """Verify the Qwen Q5 llama.cpp baseline and units are preserved."""
    tutor_data = load_yaml(BASELINES_DIR / "tutor.yaml")
    sw = tutor_data["software"]

    assert sw["model"] == "Qwen2.5 0.5B Instruct"
    assert sw["quantization"] == "Q5_K_M"
    assert sw["temperature"] == 0.0
    assert sw["max_output_tokens"] == 384
    assert sw["batch_size"] == 1
    assert sw["cpu_threads"] == 4
    assert sw["backend"] == "llama.cpp / CPU"


def test_tutor_threads_independent_of_proxy_threads():
    """Native tutor CPU threads (4) is independent of gem5 proxy threads (2). Do not impose tutor_threads <= simulated_cores."""
    tutor_data = load_yaml(BASELINES_DIR / "tutor.yaml")
    attn_data = load_yaml(BASELINES_DIR / "attention.yaml")

    tutor_threads = tutor_data["software"]["cpu_threads"]
    gem5_cores = attn_data["hardware"]["cores"]
    gem5_threads = attn_data["software"]["threads"]

    assert tutor_threads == 4
    assert gem5_cores == 2
    assert gem5_threads == 2
    # Ensure tutor threads (4) > simulated cores (2) is allowed and not rejected
    assert tutor_threads > gem5_cores


def test_model_weight_q5km_vs_proxy_kv_q4():
    """Model-weight Q5_K_M and proxy KV-cache Q4 are distinct settings."""
    tutor_data = load_yaml(BASELINES_DIR / "tutor.yaml")
    attn_data = load_yaml(BASELINES_DIR / "attention.yaml")

    assert tutor_data["software"]["quantization"] == "Q5_K_M"
    assert attn_data["software"]["kv_format"] == "Q4"


def test_runtime_ready_after_artifact_and_adapter_verification():
    """The committed contract reflects the verified server artifact path."""
    tutor_data = load_yaml(BASELINES_DIR / "tutor.yaml")
    assert tutor_data["software"]["runtime_ready"] is True
    assert tutor_data["software"]["unresolved_fields"] == []


def test_evaluation_reference_isolation_guardrail():
    """Hard guardrail: held-out evaluation references must NEVER be visible to the model."""
    tutor_data = load_yaml(BASELINES_DIR / "tutor.yaml")
    eval_cfg = tutor_data["evaluation"]
    assert eval_cfg["reference_source"] == "OpenStax College Physics 2e, Chapter 4 conceptual questions"
    assert eval_cfg["license"] == "CC BY-NC-SA 4.0"
    assert eval_cfg["reference_visible_to_model"] is False


def test_tutor_runner_rejects_invalid_candidate():
    """Invalid candidates must fail before runtime access."""
    from src.tutor.runner import run_tutor

    with pytest.raises(ValueError):
        run_tutor({})
