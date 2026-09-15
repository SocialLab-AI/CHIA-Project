from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def call_ollama(
    *,
    endpoint: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_output_tokens,
        },
    }

    request = urllib.request.Request(
        f"{endpoint}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(request) as response:
        return json.load(response)


def load_system_prompt(relative_path: str) -> str:
    path = PROJECT_ROOT / relative_path

    if not path.exists():
        raise FileNotFoundError(f"system prompt not found: {path}")

    return path.read_text(encoding="utf-8")


def extract_metrics(result: dict[str, Any]) -> dict[str, Any]:
    total_duration = result.get("total_duration", 0)
    load_duration = result.get("load_duration", 0)
    prompt_eval_duration = result.get("prompt_eval_duration", 0)
    eval_duration = result.get("eval_duration", 0)

    prompt_tokens = result.get("prompt_eval_count", 0)
    completion_tokens = result.get("eval_count", 0)

    generation_seconds = eval_duration / 1_000_000_000

    generation_tokens_per_second = (
        completion_tokens / generation_seconds
        if generation_seconds > 0
        else 0.0
    )

    return {
        "total_latency_ms": total_duration / 1_000_000,
        "load_latency_ms": load_duration / 1_000_000,
        "prompt_eval_latency_ms": prompt_eval_duration / 1_000_000,
        "generation_latency_ms": eval_duration / 1_000_000,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "generation_tokens_per_second": generation_tokens_per_second,
    }
