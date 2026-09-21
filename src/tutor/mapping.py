"""Tutor runtime mapping; software owns artifact bindings, not the optimizer."""

import re
from src.common.errors import ConfigError, PreflightError
from src.common.security import within


def map_software_candidate(software):
    """Map canonical software knobs without touching host-local runtime assets."""
    if software["batch_size"] != 1:
        raise ConfigError("Only sequential requests are currently mapped.")
    return {
        "backend": software["backend"],
        "model": software["model"],
        "weight_quantization": software["quantization"],
        "cpu_threads": software["cpu_threads"],
        "request": {
            "temperature": software["temperature"],
            "max_output_tokens": software["max_output_tokens"],
        },
        "request_concurrency": 1,
    }


def map_final_tutor(software, runtime):
    """Resolve finalized knobs without reinterpreting weight quantization as KV format."""
    candidate_mapping = map_software_candidate(software)
    required = ("assets_root", "gguf", "model_sha256", "context_tokens", "parallel_slots")
    if any(runtime.get(name) is None for name in required):
        raise PreflightError(
            "Tutor artifact, hash, context or slot bindings are incomplete."
        )
    gguf = within(runtime["assets_root"], runtime["gguf"], exists=True)
    if not re.fullmatch(r"[0-9a-f]{64}", runtime["model_sha256"]):
        raise ConfigError("Runtime model_sha256 must be a lowercase SHA-256 value.")
    for field in ("context_tokens", "parallel_slots"):
        if type(runtime[field]) is not int or runtime[field] < 1:
            raise ConfigError("Runtime context and slots must be positive integers.")
    if runtime["context_tokens"] <= software["max_output_tokens"]:
        raise ConfigError("Generation context must leave room for the prompt.")
    return {
        "endpoint": runtime["endpoint"],
        "context_tokens": runtime["context_tokens"],
        "parallel_slots": runtime["parallel_slots"],
        "cpu_threads": candidate_mapping["cpu_threads"],
        "request": {
            "model": gguf.stem,
            "temperature": software["temperature"],
            "max_output_tokens": software["max_output_tokens"],
        },
        "artifact_assertions": {
            "model": software["model"],
            "weight_quantization": software["quantization"],
            "model_path": str(gguf),
            "model_sha256": runtime["model_sha256"],
        },
        "request_concurrency": 1,
        "runtime_ready": True,
    }
