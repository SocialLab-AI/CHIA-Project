"""Immutable candidate and deterministic validation; integration owns the loop input."""

from dataclasses import dataclass
from pathlib import Path
import json
import yaml
from jsonschema import Draft202012Validator
from src.common.errors import ConfigError
from src.common.security import canonical, digest, no_secrets
from src.hardware.knobs import load_design_space, validate_hardware_candidate

ROOT = Path(__file__).resolve().parents[2]


def definition(name):
    master = yaml.safe_load(
        (ROOT / "experiment-contracts/schemas/chia-experiment.schema.yaml").read_text(
            encoding="utf-8"
        )
    )
    return {
        "$schema": master["$schema"],
        "$ref": f"#/$defs/{name}",
        "$defs": master["$defs"],
    }


def validate_schema(value, name):
    errors = list(Draft202012Validator(definition(name)).iter_errors(value))
    if errors:
        path = ".".join(str(p) for p in errors[0].absolute_path) or "root"
        raise ConfigError(f"{name} schema rejected field {path}.")


def validate_candidate(value):
    no_secrets(value)
    canonical(value)
    validate_schema(value, "loop_candidate")
    design = load_design_space()
    validate_hardware_candidate(value["hardware"], design)
    work = value["workload"]
    for field in ("query_heads", "kv_heads", "head_dimension", "layers"):
        if work[field] != design["fixed"][field]:
            raise ConfigError(f"workload.{field} is fixed by this campaign.")
    if work["context_tokens"] not in design["evaluation_axes"]["context_tokens"]:
        raise ConfigError("Context is outside the approved evaluation axes.")
    if work["query_heads"] != 4 or work["kv_heads"] != 2 or work["head_dimension"] % 2:
        raise ConfigError(
            "Current packed-Q4 kernel requires the validated four-query/two-KV shape."
        )
    if value["measurement"]["kernel_iterations"] != design["fixed"]["repetitions"]:
        raise ConfigError("Kernel iterations are fixed by the hardware campaign.")
    space = yaml.safe_load(
        (ROOT / "experiment-contracts/testing/software-design-space.yaml").read_text()
    )
    software = value["software"]
    for field, choices in space["active_candidates"].items():
        if software[field] not in choices:
            raise ConfigError(f"software.{field} is outside the testing design space.")
    for field, fixed in space["fixed"].items():
        if software[field] != fixed:
            raise ConfigError(f"software.{field} is fixed for the test profile.")
    return value


@dataclass(frozen=True)
class Candidate:
    """A JSON snapshot prevents caller mutation after validation or during execution."""

    payload: str

    @classmethod
    def from_dict(cls, value):
        snapshot = json.loads(canonical(value))
        validate_candidate(snapshot)
        return cls(canonical(snapshot))

    @property
    def config(self):
        return json.loads(self.payload)

    @property
    def candidate_id(self):
        return digest(self.config)


def baseline_candidate():
    attention = yaml.safe_load(
        (ROOT / "experiment-contracts/baselines/attention.yaml").read_text()
    )
    return {
        "schema_version": "0.3.0",
        "profile": "qwen25-q5-openstax",
        "hardware": attention["hardware"],
        "software": {
            "model": "Qwen2.5 0.5B Instruct",
            "quantization": "Q5_K_M",
            "backend": "llama.cpp / CPU",
            "temperature": 0.0,
            "max_output_tokens": 384,
            "cpu_threads": 4,
            "batch_size": 1,
        },
        "workload": attention["workload"],
        "measurement": {"software_repetitions": 1, "kernel_iterations": 10},
    }
