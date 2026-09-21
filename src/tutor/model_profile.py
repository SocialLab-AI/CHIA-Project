"""Extract verified GGUF architecture metadata; Tutor owns model identity."""

from __future__ import annotations

import hashlib
import gc
from pathlib import Path

from src.common.errors import ConfigError, PreflightError
from src.tutor.llama_cpp_runtime import file_sha256


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"GGUF metadata {name} must be nonempty text.")
    return value.strip()


def _positive_integer(value, name):
    if isinstance(value, bool):
        raise ConfigError(f"GGUF metadata {name} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigError(
            f"GGUF metadata {name} must be a positive integer."
        ) from error
    if parsed < 1:
        raise ConfigError(f"GGUF metadata {name} must be a positive integer.")
    return parsed


def _nonnegative_integer(value, name):
    if isinstance(value, bool):
        raise ConfigError(f"GGUF metadata {name} must be a nonnegative integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigError(
            f"GGUF metadata {name} must be a nonnegative integer."
        ) from error
    if parsed < 0:
        raise ConfigError(f"GGUF metadata {name} must be a nonnegative integer.")
    return parsed


def extract_gguf_profile(model_path, expected_sha256=None):
    """Read the selected GGUF header and return architecture evidence."""

    try:
        from gguf import GGUFReader, LlamaFileType
    except ImportError as error:
        raise PreflightError(
            "Install the calibration extra before reading GGUF metadata."
        ) from error

    path = Path(model_path).expanduser().resolve()
    if not path.is_file() or path.suffix.casefold() != ".gguf":
        raise PreflightError("The configured GGUF model file does not exist.")
    actual_sha256 = file_sha256(path)
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise PreflightError("GGUF SHA-256 differs from the reviewed artifact.")

    reader = GGUFReader(path, "r")

    def optional(key):
        field = reader.get_field(key)
        return None if field is None else field.contents()

    def required(key):
        value = optional(key)
        if value is None:
            raise ConfigError(f"Required GGUF metadata is absent: {key}.")
        return value

    architecture = _text(required("general.architecture"), "general.architecture")
    prefix = architecture + "."
    layers = _positive_integer(required(prefix + "block_count"), "block_count")
    hidden = _positive_integer(required(prefix + "embedding_length"), "embedding_length")
    query_heads = _positive_integer(
        required(prefix + "attention.head_count"), "attention.head_count"
    )
    kv_heads = _positive_integer(
        required(prefix + "attention.head_count_kv"), "attention.head_count_kv"
    )
    feed_forward = _positive_integer(
        required(prefix + "feed_forward_length"), "feed_forward_length"
    )
    maximum_context = _positive_integer(
        required(prefix + "context_length"), "context_length"
    )
    explicit_head_dimension = optional(prefix + "attention.key_length")
    if explicit_head_dimension is None:
        explicit_head_dimension = optional(prefix + "rope.dimension_count")
    if explicit_head_dimension is None:
        if hidden % query_heads:
            raise ConfigError(
                "Cannot derive attention head dimension from GGUF metadata."
            )
        head_dimension = hidden // query_heads
        head_dimension_source = "embedding_length/query_heads"
    else:
        head_dimension = _positive_integer(
            explicit_head_dimension, "attention head dimension"
        )
        head_dimension_source = (
            "attention.key_length"
            if optional(prefix + "attention.key_length") is not None
            else "rope.dimension_count"
        )

    file_type_code = _nonnegative_integer(
        required("general.file_type"), "general.file_type"
    )
    try:
        quantization = LlamaFileType(file_type_code).name.removeprefix("MOSTLY_")
    except ValueError:
        quantization = f"UNKNOWN_FILE_TYPE_{file_type_code}"
    chat_template = optional("tokenizer.chat_template")
    if chat_template is not None and not isinstance(chat_template, str):
        raise ConfigError("GGUF chat template must be text when present.")

    tensor_parameters = sum(int(tensor.n_elements) for tensor in reader.tensors)
    result = {
        "schema_version": "0.1.0",
        "model_path": str(path),
        "model_sha256": actual_sha256,
        "model_name": optional("general.name"),
        "architecture": architecture,
        "layers": layers,
        "hidden_size": hidden,
        "query_heads": query_heads,
        "kv_heads": kv_heads,
        "head_dimension": head_dimension,
        "head_dimension_source": head_dimension_source,
        "feed_forward_dimension": feed_forward,
        "maximum_context_length": maximum_context,
        "quantization": quantization,
        "gguf_file_type": file_type_code,
        "quantization_version": optional("general.quantization_version"),
        "parameter_count_from_tensor_shapes": tensor_parameters,
        "chat_template_present": chat_template is not None,
        "chat_template_sha256": (
            hashlib.sha256(chat_template.encode("utf-8")).hexdigest()
            if chat_template is not None
            else None
        ),
        "kv_cache_quantization": "runtime-dependent",
    }
    # GGUFReader memory-maps the model. Release it before returning so Windows
    # tests and operators can move or delete temporary GGUF files immediately.
    del reader
    gc.collect()
    return result
