"""Deterministic trust boundaries; integration owns paths, JSON, endpoints and redaction."""

import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit
from src.common.errors import ConfigError

SECRET = re.compile(
    r"(?i)(api[_-]?key|password|secret|authorization|access[_-]?token|private[_-]?key)"
)


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value
    ):
        raise ConfigError(
            "Identifier must start with a letter/digit and contain only letters, digits, underscores or hyphens."
        )
    return value


def within(root, path, *, exists=False):
    root = Path(root).resolve()
    path = Path(path)
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ConfigError("Path must be a child of the configured artifact root.")
    if exists and not resolved.is_file():
        raise ConfigError("Required artifact file does not exist.")
    return resolved


def strict_json(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 262144:
        raise ConfigError("JSON response exceeds the size limit.")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ConfigError("Duplicate JSON keys are forbidden.")
            result[key] = value
        return result

    def bad_constant(value):
        raise ConfigError("Non-finite JSON values are forbidden.")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)
    except (ValueError, RecursionError) as exc:
        raise ConfigError("Expected one strict JSON value.") from exc


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ConfigError("Candidate is not finite JSON data.") from exc


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def no_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET.search(str(key)):
                raise ConfigError(
                    "Credential fields are forbidden in candidates and run records."
                )
            no_secrets(item)
    elif isinstance(value, list):
        for item in value:
            no_secrets(item)
    elif isinstance(value, str) and (
        "PRIVATE KEY-----" in value or re.search(r"AIza[0-9A-Za-z_-]{30,}", value)
    ):
        raise ConfigError("Credential material is forbidden.")


def local_endpoint(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ConfigError(
            "Runtime endpoint must be a loopback HTTP origin with no credentials."
        )
    try:
        parsed.port
    except ValueError as exc:
        raise ConfigError("Invalid runtime port.") from exc
    return value.rstrip("/")


def safe_output(text):
    """Summarize untrusted output without copying any of its content into shared logs."""
    data = (text or "").encode("utf-8", errors="replace")
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content": "[omitted]",
    }


def finite_number(value, name, *, positive=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or (positive and value == 0)
    ):
        raise ConfigError(
            f"{name} must be a finite {'positive' if positive else 'nonnegative'} number."
        )
    return value
