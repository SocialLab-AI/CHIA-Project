"""Tests for proposals, metering, and runtime isolation."""

import json
from types import SimpleNamespace

import pytest

from src.common.candidate import Candidate, baseline_candidate
from src.common.errors import (
    ConfigError,
    OptimizerError,
    PreflightError,
)
from src.hardware.knobs import load_design_space
from src.orchestration.gemini_api import (
    estimate_cost_usd,
    extract_usage,
    parse_proposal,
)
from src.tutor.mapping import map_final_tutor


def valid_proposal():
    candidate = baseline_candidate()

    hardware_knobs = load_design_space()[
        "active_candidates"
    ]["hardware"]

    return {
        "hardware": {
            knob: candidate["hardware"][knob]
            for knob in hardware_knobs
        },
        "software": {
            knob: candidate["software"][knob]
            for knob in (
                "temperature",
                "max_output_tokens",
            )
        },
    }


def test_strict_active_proposal():
    candidate = parse_proposal(
        json.dumps(valid_proposal())
    )

    assert Candidate.from_dict(candidate).candidate_id


def test_proposal_extra_field_rejected():
    proposal = valid_proposal()
    proposal["hardware"]["command"] = "delete"

    with pytest.raises(
        (ConfigError, OptimizerError)
    ):
        parse_proposal(json.dumps(proposal))


def test_duplicate_proposal_rejected():
    baseline_id = Candidate.from_dict(
        baseline_candidate()
    ).candidate_id

    with pytest.raises(OptimizerError):
        parse_proposal(
            json.dumps(valid_proposal()),
            {baseline_id},
        )


def test_usage_and_cost_are_metered():
    api_response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=422,
            candidates_token_count=221,
            thoughts_token_count=0,
            total_token_count=643,
        )
    )

    usage = extract_usage(api_response)

    assert usage == {
        "input_tokens": 422,
        "candidate_tokens": 221,
        "thought_tokens": 0,
        "output_tokens": 221,
        "total_tokens": 643,
    }

    cost = estimate_cost_usd(
        usage,
        input_usd_per_million_tokens=0.25,
        output_usd_per_million_tokens=1.50,
    )

    assert cost == pytest.approx(0.000437)


def test_final_runtime_does_not_invent_missing_assets():
    import yaml

    from src.common.candidate import ROOT

    software = yaml.safe_load(
        (
            ROOT
            / "experiment-contracts"
            / "baselines"
            / "tutor.yaml"
        ).read_text(encoding="utf-8")
    )["software"]

    with pytest.raises(PreflightError):
        map_final_tutor(software, {})
