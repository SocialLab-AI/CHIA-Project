from pathlib import Path
import json
import pytest
import yaml

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "experiment-contracts"
AI_TUTOR_DIR = CONTRACTS / "ai-tutor-config"
ATTN_DIR = CONTRACTS / "attention-experiments"
SCHEMAS_DIR = CONTRACTS / "schemas"


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
def tutor_validator(registry):
    schema = load_json(AI_TUTOR_DIR / "ai-tutor.schema.json")
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def test_tutor_example_validates(tutor_validator):
    tutor_data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")
    errors = list(tutor_validator.iter_errors(tutor_data))
    assert not errors, f"example.ai-tutor.yaml failed validation: {[e.message for e in errors]}"


def test_user_supplied_software_baseline_values():
    """Verify all 13 user-supplied software baseline values and units are preserved."""
    tutor_data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")
    sw = tutor_data["software"]

    assert sw["model"] == "Llama 3.2 1B Instruct"
    assert sw["quantization"] == "Q4_K_M"
    assert sw["embedding_model"] == "MiniLM-L6-dot-v1"
    assert sw["embedding_dimension"] == 384
    assert sw["retrieval_method"] == "Semantic similarity"
    assert sw["top_k"] == 2
    assert sw["chunk_size"] == 1500
    assert sw["chunk_overlap"] == 200
    assert sw["chunk_unit"] == "characters"
    assert sw["temperature"] == 0.0
    assert sw["max_output_tokens"] == 384
    assert sw["batch_size"] == 1
    assert sw["cpu_threads"] == 4
    assert sw["backend"] == "llama.cpp / CPU"


def test_chunk_size_and_overlap_character_units():
    """Chunk size and overlap must be measured in CHARACTERS, not tokens."""
    tutor_data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")
    sw = tutor_data["software"]
    assert sw["chunk_unit"] == "characters"
    assert sw["chunk_size"] == 1500
    assert sw["chunk_overlap"] == 200
    assert sw["chunk_overlap"] < sw["chunk_size"]


def test_tutor_threads_independent_of_proxy_threads():
    """Native tutor CPU threads (4) is independent of gem5 proxy threads (2). Do not impose tutor_threads <= simulated_cores."""
    tutor_data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")
    attn_data = load_yaml(ATTN_DIR / "baseline.attention.yaml")

    tutor_threads = tutor_data["software"]["cpu_threads"]
    gem5_cores = attn_data["hardware"]["cores"]
    gem5_threads = attn_data["software"]["threads"]

    assert tutor_threads == 4
    assert gem5_cores == 2
    assert gem5_threads == 2
    # Ensure tutor threads (4) > simulated cores (2) is allowed and not rejected
    assert tutor_threads > gem5_cores


def test_model_weight_q4km_vs_proxy_kv_q4():
    """Model-weight Q4_K_M and proxy KV-cache Q4 are distinct settings."""
    tutor_data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")
    attn_data = load_yaml(ATTN_DIR / "baseline.attention.yaml")

    assert tutor_data["software"]["quantization"] == "Q4_K_M"
    assert attn_data["software"]["kv_format"] == "Q4"


def test_runtime_ready_false_without_artifacts():
    """Missing runtime artifacts do not permit execution-ready status (runtime_ready must be False)."""
    tutor_data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")
    assert tutor_data["software"]["runtime_ready"] is False
    assert len(tutor_data["software"]["unresolved_fields"]) > 0


def test_openstax_evaluation_reference_isolation():
    """Hard guardrail: OpenStax evaluation reference answers must NEVER be visible to the model."""
    tutor_data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")
    eval_cfg = tutor_data["evaluation"]
    assert eval_cfg["reference_source"] == "openstax"
    assert eval_cfg["reference_visible_to_model"] is False


def test_application_latency_distinct_from_simulated_latency():
    """Verify application latency (latency_ms) is separate from simulated hardware time."""
    tutor_data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")
    attn_data = load_yaml(ATTN_DIR / "baseline.attention.yaml")

    assert "application" in tutor_data["metrics"]
    assert "latency_ms" in tutor_data["metrics"]["application"]
    # Simulated metrics are in attention experiment, not tutor metrics
    assert "sim_ticks" not in tutor_data["metrics"]["application"]
    assert "sim_ticks" in attn_data["metrics"]


def test_tutor_runner_skeleton():
    """Verify src.tutor.runner raises NotImplementedError."""
    from src.tutor.runner import run_tutor
    with pytest.raises(NotImplementedError):
        run_tutor({})
