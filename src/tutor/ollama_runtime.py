"""Ollama HTTP adapter; software owns inference transport used by the software node."""

from __future__ import annotations
import json
import urllib.error
import urllib.request
from pathlib import Path
from src.common.errors import (
    PreflightError,
    RuntimeExecutionError,
    TransientRuntimeError,
    ExecutionTimeout,
)
from src.common.security import local_endpoint, strict_json, within

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeExecutionError("Runtime HTTP redirects are forbidden.")


def request_json(endpoint, route, payload=None, *, timeout=120):
    endpoint = local_endpoint(endpoint)
    request = urllib.request.Request(
        endpoint + route,
        data=None if payload is None else json.dumps(payload, allow_nan=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    # Ignore host proxy variables for the local runtime; redirects must not escape loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            data = response.read(262145)
            if len(data) > 262144:
                raise RuntimeExecutionError("Runtime response exceeds the limit.")
            result = strict_json(data.decode("utf-8"))
            if not isinstance(result, dict) or "error" in result:
                raise RuntimeExecutionError(
                    "Runtime returned an error or malformed object."
                )
            return result
    except urllib.error.HTTPError as exc:
        if exc.code in {429, 502, 503, 504}:
            raise TransientRuntimeError(
                "Local runtime temporarily unavailable."
            ) from exc
        raise RuntimeExecutionError(
            f"Runtime HTTP request failed with status {exc.code}."
        ) from exc
    except (TimeoutError,):
        raise ExecutionTimeout("Local runtime request timed out.") from None
    except urllib.error.URLError as exc:
        raise TransientRuntimeError("Cannot connect to the local runtime.") from exc


def preflight(endpoint, model, *, expected_digest=None, timeout=10):
    version = request_json(endpoint, "/api/version", timeout=timeout).get("version")
    tags = request_json(endpoint, "/api/tags", timeout=timeout).get("models", [])
    match = next(
        (m for m in tags if m.get("name") == model or m.get("model") == model), None
    )
    if not version or not match or not match.get("digest"):
        raise PreflightError(
            "Required Ollama version/model digest is unavailable; no model is downloaded automatically."
        )
    if expected_digest and match["digest"] != expected_digest:
        raise PreflightError("Ollama model digest differs from the pinned artifact.")
    return {
        "runtime": "ollama",
        "runtime_version": version,
        "model_id": model,
        "model_digest": match["digest"],
    }


def call_ollama(
    *,
    endpoint,
    model,
    system_prompt,
    user_prompt,
    temperature,
    max_output_tokens,
    cpu_threads=4,
    timeout=120,
):
    return request_json(
        endpoint,
        "/api/generate",
        {
            "model": model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_output_tokens,
                "num_thread": cpu_threads,
            },
        },
        timeout=timeout,
    )


def load_system_prompt(relative_path):
    return within(PROJECT_ROOT, relative_path, exists=True).read_text(encoding="utf-8")


def extract_metrics(result):
    from src.tutor.metrics import extract_generation_metrics

    return extract_generation_metrics(result)
