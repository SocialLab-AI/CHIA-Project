import json

import pytest

from src.common.candidate import Candidate
from src.common.errors import OptimizerError
from src.orchestration.gemini_api import (
    parse_software_proposal,
    software_proposal_schema,
)


def test_software_schema_has_no_hardware():
    schema = software_proposal_schema()

    assert schema["required"] == ["software"]
    assert set(schema["properties"]) == {"software"}


def test_software_schema_contains_exact_active_knobs():
    schema = software_proposal_schema()

    software = schema["properties"]["software"]

    assert set(software["required"]) == {
        "temperature",
        "max_output_tokens",
    }


def test_valid_software_proposal_builds_complete_candidate():
    proposal = json.dumps(
        {
            "software": {
                "temperature": 0.2,
                "max_output_tokens": 128,
            }
        }
    )

    candidate = parse_software_proposal(
        proposal,
        software_repetitions=1,
    )

    assert candidate["software"]["temperature"] == 0.2
    assert candidate["software"]["max_output_tokens"] == 128

    # Fixed values must still come from the canonical baseline.
    assert candidate["software"]["model"] == (
        "Qwen2.5 0.5B Instruct"
    )
    assert candidate["software"]["quantization"] == "Q5_K_M"
    assert candidate["software"]["cpu_threads"] == 4
    assert candidate["software"]["batch_size"] == 1

    Candidate.from_dict(candidate)


def test_invalid_software_value_is_rejected():
    proposal = json.dumps(
        {
            "software": {
                "temperature": 1.9,
                "max_output_tokens": 128,
            }
        }
    )

    with pytest.raises(Exception):
        parse_software_proposal(proposal)


def test_hardware_in_software_proposal_is_rejected():
    proposal = json.dumps(
        {
            "hardware": {},
            "software": {
                "temperature": 0.2,
                "max_output_tokens": 128,
            },
        }
    )

    with pytest.raises(OptimizerError):
        parse_software_proposal(proposal)


def test_duplicate_candidate_is_rejected():
    proposal = json.dumps(
        {
            "software": {
                "temperature": 0.2,
                "max_output_tokens": 128,
            }
        }
    )

    candidate = parse_software_proposal(proposal)

    candidate_id = Candidate.from_dict(
        candidate
    ).candidate_id

    with pytest.raises(OptimizerError):
        parse_software_proposal(
            proposal,
            seen={candidate_id},
        )
