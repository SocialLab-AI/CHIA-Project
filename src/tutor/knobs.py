from __future__ import annotations

from typing import Any


class SoftwareConfigError(ValueError):
    pass


def validate_software_candidate(config: dict[str, Any]) -> None:
    software = config["software"]

    temperature = software["temperature"]
    max_output_tokens = software["max_output_tokens"]

    if isinstance(temperature, bool) or not isinstance(
        temperature, (int, float)
    ):
        raise SoftwareConfigError("temperature must be numeric")

    if temperature < 0.0 or temperature > 2.0:
        raise SoftwareConfigError(
            "temperature must be between 0.0 and 2.0"
        )

    if (
        isinstance(max_output_tokens, bool)
        or not isinstance(max_output_tokens, int)
        or max_output_tokens < 1
    ):
        raise SoftwareConfigError(
            "max_output_tokens must be a positive integer"
        )
