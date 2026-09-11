from pathlib import Path
import json
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "configs" / "schemas"
SOFTWARE = ROOT / "configs" / "software"
EXAMPLES = ROOT / "configs" / "examples"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def validators():
    schema_files = {
        "chia-experiment.schema.json": load_json(SCHEMAS / "chia-experiment.schema.json"),
        "experiment.schema.json": load_json(SCHEMAS / "experiment.schema.json"),
        "design-space.schema.json": load_json(SCHEMAS / "design-space.schema.json"),
        "run-record.schema.json": load_json(SCHEMAS / "run-record.schema.json"),
    }
    registry = Registry()
    for name, schema in schema_files.items():
        res = Resource.from_contents(schema)
        registry = registry.with_resource(name, res)
        if "$id" in schema:
            registry = registry.with_resource(schema["$id"], res)

    sw_val = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/software_config"},
        registry=registry,
        format_checker=FormatChecker()
    )
    sw_ds_val = Draft202012Validator(
        {"$ref": "chia-experiment.schema.json#/$defs/software_design_space"},
        registry=registry,
        format_checker=FormatChecker()
    )
    exp_val = Draft202012Validator(
        schema_files["experiment.schema.json"],
        registry=registry,
        format_checker=FormatChecker()
    )
    return sw_val, sw_ds_val, exp_val


def test_software_design_space_valid(validators):
    _, sw_ds_val, _ = validators
    ds = load_json(SOFTWARE / "design-space.software.json")
    errors = list(sw_ds_val.iter_errors(ds))
    assert not errors, f"design-space.software.json failed validation: {[e.message for e in errors]}"


def test_active_knobs_exact_count_and_members():
    ds = load_json(SOFTWARE / "design-space.software.json")
    active_knobs = ds["active_knobs"]
    assert len(active_knobs) == 4, f"Expected exactly 4 active software knobs, got {len(active_knobs)}"
    assert set(active_knobs.keys()) == {"temperature", "chunk_overlap", "similarity_metric", "quantization"}

    # Metrics MUST NOT be in active knobs
    assert "answer_quality" not in active_knobs
    assert "latency_ms" not in active_knobs
    assert "quality" not in active_knobs
    assert "latency" not in active_knobs

    # Units
    assert active_knobs["chunk_overlap"]["unit"] == "tokens"
    assert active_knobs["temperature"]["unit"] == "unitless"


def test_fixed_software_parameters():
    ds = load_json(SOFTWARE / "design-space.software.json")
    fixed = ds["fixed_parameters"]
    assert fixed["runtime"] == "ollama"
    assert fixed["parameter_count"] == "1B"
    assert fixed["rag_enabled"] is True


def test_optimization_metrics_directions():
    ds = load_json(SOFTWARE / "design-space.software.json")
    metrics = ds["optimization_metrics"]
    assert "answer_quality" in metrics
    assert "latency_ms" in metrics
    assert metrics["answer_quality"]["direction"] == "maximize"
    assert metrics["latency_ms"]["direction"] == "minimize"


def test_baseline_software_is_draft_not_execution_ready(validators):
    sw_val, _, _ = validators
    baseline = load_json(SOFTWARE / "baseline.software.json")

    # Draft metadata assertions
    assert baseline["status"] == "draft"
    assert baseline["runtime_ready"] is False
    assert baseline["runtime"] == "ollama"
    assert baseline["parameter_count"] == "1B"
    assert baseline["rag"]["enabled"] is True

    # Check that it validates cleanly against master schema software_config as draft
    errors = list(sw_val.iter_errors(baseline))
    assert not errors, f"baseline.software.json failed validation: {[e.message for e in errors]}"

    # Verify 13 unresolved fields are documented
    unresolved = baseline["unresolved_fields"]
    assert len(unresolved) == 13
    assert "exact 1B Ollama model artifact" in unresolved
    assert "temperature baseline and legal values" in unresolved
    assert "chunk_overlap baseline and legal values" in unresolved
    assert "similarity_metric baseline and legal values" in unresolved
    assert "quantization baseline and legal values" in unresolved
    assert "embedding model" in unresolved
    assert "chunk size" in unresolved
    assert "retrieval top-k" in unresolved
    assert "max context tokens" in unresolved
    assert "max new tokens" in unresolved
    assert "batch size" in unresolved
    assert "seed" in unresolved
    assert "exact RAG corpus" in unresolved


def test_execution_ready_schema_requires_concrete_types(validators):
    sw_val, _, _ = validators

    # A mock concrete execution-ready software configuration
    mock_ready_candidate = {
        "runtime": "ollama",
        "parameter_count": "1B",
        "model": "qwen2.5:1b-instruct",
        "quantization": "q4_k_m",
        "runtime_ready": True,
        "prompt": {
            "system_prompt_file": "prompts/tutor_system.txt"
        },
        "generation": {
            "temperature": 0.7,
            "max_context_tokens": 2048,
            "max_new_tokens": 256,
            "batch_size": 1,
            "seed": 42
        },
        "rag": {
            "enabled": True,
            "embedding_model": "nomic-embed-text",
            "chunk_size": 256,
            "chunk_overlap": 32,
            "retrieval_top_k": 3,
            "similarity_metric": "cosine"
        },
        "metrics": {
          "application": {
            "answer_quality": None,
            "latency_ms": None
          }
        }
    }
    errors = list(sw_val.iter_errors(mock_ready_candidate))
    assert not errors, f"Valid execution-ready candidate failed: {[e.message for e in errors]}"

    # Negative test: placing string into numeric temperature without draft status fails
    invalid_candidate = json.loads(json.dumps(mock_ready_candidate))
    invalid_candidate["generation"]["temperature"] = "pending_definition"
    errors = list(sw_val.iter_errors(invalid_candidate))
    assert len(errors) > 0, "Schema improperly accepted string for numeric temperature"

    # Negative test: draft claiming runtime_ready=True fails
    invalid_draft = {
        "status": "draft",
        "runtime_ready": True,
        "runtime": "ollama",
        "parameter_count": "1B",
        "rag": {"enabled": True},
        "unresolved_fields": ["model"]
    }
    errors = list(sw_val.iter_errors(invalid_draft))
    assert len(errors) > 0, "Schema improperly accepted draft with runtime_ready=True"


def test_experiment_examples_with_software_and_metrics(validators):
    _, _, exp_val = validators
    for example_file in sorted(EXAMPLES.glob("*.json")):
        example = load_json(example_file)
        errors = list(exp_val.iter_errors(example))
        assert not errors, f"{example_file.name} failed validation: {[e.message for e in errors]}"
        assert "objectives" in example
        assert example["objectives"]["answer_quality"] == "maximize"
        assert example["objectives"]["latency_ms"] == "minimize"
        assert "metrics" in example
        assert example["metrics"]["application"]["answer_quality"] is None
        assert example["metrics"]["application"]["latency_ms"] is None
