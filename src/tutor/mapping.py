"""Final Tutor runtime mapping contract; software owns inference artifact bindings, not the optimizer."""

from src.common.errors import ConfigError, PreflightError
from src.common.security import within


def map_final_tutor(software, runtime):
    """Resolve finalized knobs without reinterpreting weight quantization as KV format."""
    if software["batch_size"] != 1:
        raise ConfigError("Only sequential requests are currently mapped.")
    required = (
        "assets_root",
        "gguf",
        "context_tokens",
        "token_batch_size",
        "physical_batch_size",
    )
    if any(runtime.get(name) is None for name in required):
        raise PreflightError(
            "Final Tutor artifact/context/token-batching bindings are incomplete."
        )
    gguf = within(runtime["assets_root"], runtime["gguf"], exists=True)
    for field in ("context_tokens", "token_batch_size", "physical_batch_size"):
        if type(runtime[field]) is not int or runtime[field] < 1:
            raise ConfigError(
                "Runtime batching/context limits must be positive integers."
            )
    if runtime["context_tokens"] <= software["max_output_tokens"]:
        raise ConfigError("Generation context must leave room for the prompt.")
    if runtime["physical_batch_size"] > runtime["token_batch_size"]:
        raise ConfigError("Physical batch cannot exceed logical token batch.")
    return {
        "llama_cpp_argv": [
            "--model",
            str(gguf),
            "--threads",
            str(software["cpu_threads"]),
            "--temp",
            str(software["temperature"]),
            "--predict",
            str(software["max_output_tokens"]),
            "--ctx-size",
            str(runtime["context_tokens"]),
            "--batch-size",
            str(runtime["token_batch_size"]),
            "--ubatch-size",
            str(runtime["physical_batch_size"]),
        ],
        "artifact_assertions": {
            "model": software["model"],
            "weight_quantization": software["quantization"],
        },
        "request_concurrency": 1,
        "runtime_ready": False,
        "remaining_gate": "Verify GGUF metadata and hashes, tokenizer budgets, held-out evaluator and proxy mapping.",
    }
