"""Gemini optimizer for proposing hardware configurations."""

import json
import os
from typing import Any

from google import genai
from google.genai import types


from src.hardware.knobs import (
    baseline_hardware_candidate,
    validate_hardware_candidate,
)


SYSTEM_MESSAGE = """
You optimize simulated CPU hardware for an offline edge AI tutor.

Propose exactly one hardware configuration that balances:
- low simulated latency
- low memory traffic
- high IPC
- low hardware cost

Rules:
1. Use only values from active_candidates.hardware.
2. Do not modify fixed values.
3. Do not repeat a configuration in previous_experiments.
4. RiscvTimingSimpleCPU requires issue_width=1.
5. Return only a JSON object containing the active hardware knobs.
6. Do not return Markdown or an explanation.
"""


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract one JSON object from Gemini's response."""
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("optimizer response did not contain JSON")

    value = json.loads(text[start : end + 1])

    if not isinstance(value, dict):
        raise ValueError("optimizer response must be a JSON object")

    if "hardware" in value:
        value = value["hardware"]

    if not isinstance(value, dict):
        raise ValueError("hardware candidate must be a JSON object")

    return value


def propose_hardware_candidate(
    design_space: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Ask Gemini for one valid hardware candidate."""

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    selected_model = (
        model
        or os.getenv("CHIA_OPTIMIZER_MODEL")
        or "gemini-3.1-flash-lite"
    )

    request = {
        "active_hardware_knobs": (
            design_space["active_candidates"]["hardware"]
        ),
        "fixed_values": design_space["fixed"],
        "constraints": design_space.get("constraints", []),
        "previous_experiments": history or [],
        "instruction": "Return the next hardware candidate as JSON.",
    }

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=selected_model,
        contents=json.dumps(request),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_MESSAGE,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    proposed_active = _parse_json_response(response.text or "")

    candidate = baseline_hardware_candidate(design_space)

    for knob in design_space["active_candidates"]["hardware"]:
        if knob not in proposed_active:
            raise ValueError(
                f"Gemini response is missing hardware knob: {knob}"
            )

        candidate[knob] = proposed_active[knob]

    validate_hardware_candidate(candidate, design_space)

    return candidate
