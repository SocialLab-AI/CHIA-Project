"""Orchestration policy tests for the active Gemini SDK path."""

import pytest
from src.orchestration.chia import chia_entrypoint
from src.orchestration.gemini_api import proposal_schema


def test_gemini_schema_has_closed_hardware_and_software_objects():
    schema = proposal_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["hardware", "software"]
    assert schema["properties"]["hardware"]["additionalProperties"] is False
    assert schema["properties"]["software"]["additionalProperties"] is False


def test_iterations_rejected_before_execution():
    with pytest.raises(ValueError):
        chia_entrypoint({"iterations": 0})


def test_unknown_backend_rejected_before_execution():
    with pytest.raises(ValueError):
        chia_entrypoint({"backend": "unapproved"})
