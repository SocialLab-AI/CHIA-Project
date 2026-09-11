from pathlib import Path
import json
import pytest

try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

ROOT = Path(__file__).resolve().parents[1]
SOFTWARE = ROOT / "configs" / "software"
EXAMPLES = ROOT / "configs" / "examples"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_tutor_yaml_files_exist():
    baseline_yaml = SOFTWARE / "baseline.software.yaml"
    ds_yaml = SOFTWARE / "design-space.software.yaml"
    assert baseline_yaml.exists()
    assert ds_yaml.exists()
    assert "status: draft" in baseline_yaml.read_text(encoding="utf-8")
    assert "active_knobs:" in ds_yaml.read_text(encoding="utf-8")


@pytest.mark.skipif(not HAVE_YAML, reason="PyYAML not installed in default test venv")
def test_tutor_json_yaml_parity():
    baseline_json = load_json(SOFTWARE / "baseline.software.json")
    baseline_yaml = yaml.safe_load((SOFTWARE / "baseline.software.yaml").read_text(encoding="utf-8"))
    assert baseline_json == baseline_yaml, "baseline.software.json and baseline.software.yaml must match"

    ds_json = load_json(SOFTWARE / "design-space.software.json")
    ds_yaml = yaml.safe_load((SOFTWARE / "design-space.software.yaml").read_text(encoding="utf-8"))
    assert ds_json == ds_yaml, "design-space.software.json and design-space.software.yaml must match"


def test_tutor_rag_pipeline_confirmed():
    ds = load_json(SOFTWARE / "design-space.software.json")
    assert ds["fixed_parameters"]["runtime"] == "ollama"
    assert ds["fixed_parameters"]["parameter_count"] == "1B"
    assert ds["fixed_parameters"]["rag_enabled"] is True


def test_tutor_active_knobs_and_objectives():
    ds = load_json(SOFTWARE / "design-space.software.json")
    assert set(ds["active_knobs"].keys()) == {
        "temperature",
        "chunk_overlap",
        "similarity_metric",
        "quantization"
    }

    metrics = ds["optimization_metrics"]
    assert metrics["answer_quality"]["direction"] == "maximize"
    assert metrics["latency_ms"]["direction"] == "minimize"


def test_openstax_evaluation_guardrail():
    for example_file in EXAMPLES.glob("*.json"):
        data = load_json(example_file)
        eval_cfg = data["evaluation"]
        assert eval_cfg["reference_source"] == "openstax"
        assert eval_cfg["reference_visible_to_model"] is False, "Guardrail violation: OpenStax must NOT be visible to model"


@pytest.mark.skipif(not HAVE_YAML, reason="PyYAML not installed in default test venv")
def test_experiment_contracts_examples_valid():
    from referencing import Registry, Resource
    from jsonschema import Draft202012Validator, FormatChecker

    contracts = ROOT / "experiment-contracts"
    chia_schema = load_json(ROOT / "configs" / "schemas" / "chia-experiment.schema.json")
    res = Resource.from_contents(chia_schema)
    reg = Registry().with_resource(chia_schema["$id"], res).with_resource("chia-experiment.schema.json", res)

    cases = [
        (contracts / "ai-tutor-config" / "example.ai-tutor.yaml",
         contracts / "ai-tutor-config" / "ai-tutor.schema.json"),
        (contracts / "attention-experiments" / "baseline.attention.yaml",
         contracts / "attention-experiments" / "attention-experiment.schema.json"),
        (contracts / "attention-experiments" / "example.candidate.yaml",
         contracts / "attention-experiments" / "attention-experiment.schema.json"),
        (contracts / "attention-experiments" / "design-space.yaml",
         contracts / "attention-experiments" / "attention-design-space.schema.json"),
        (contracts / "run-records" / "example.completed.yaml",
         contracts / "run-records" / "run-record.schema.json"),
    ]
    for data_path, schema_path in cases:
        data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
        schema = load_json(schema_path)
        validator = Draft202012Validator(schema, registry=reg, format_checker=FormatChecker())
        errors = list(validator.iter_errors(data))
        assert not errors, f"{data_path.name} failed schema {schema_path.name}: {[e.message for e in errors]}"

