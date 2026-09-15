"""Untrusted proposal and reference-isolation tests; integration owns activation gates."""

import json
import pytest
from src.common.candidate import baseline_candidate, Candidate
from src.hardware.knobs import load_design_space
from src.orchestration.gemini_cli import parse_proposal
from src.common.errors import ConfigError, OptimizerError, PreflightError
from src.tutor.mapping import map_final_tutor


def response():
    c = baseline_candidate()
    return {
        "hardware": {
            k: c["hardware"][k]
            for k in load_design_space()["active_candidates"]["hardware"]
        },
        "software": {k: c["software"][k] for k in ("temperature", "max_output_tokens")},
    }


def test_strict_active_proposal():
    c, usage = parse_proposal(
        json.dumps(
            {
                "response": json.dumps(response()),
                "stats": {"tokens": 2, "log": "untrusted"},
            }
        )
    )
    assert Candidate.from_dict(c).candidate_id
    assert "log" not in usage


def test_proposal_extra_field_and_duplicate_rejected():
    data = response()
    data["hardware"]["command"] = "delete"
    with pytest.raises((ConfigError, OptimizerError)):
        parse_proposal(json.dumps({"response": json.dumps(data)}))
    with pytest.raises(OptimizerError):
        parse_proposal(
            json.dumps({"response": json.dumps(response())}),
            {Candidate.from_dict(baseline_candidate()).candidate_id},
        )


def test_final_runtime_does_not_invent_missing_assets():
    import yaml
    from src.common.candidate import ROOT

    software = yaml.safe_load(
        (ROOT / "experiment-contracts/baselines/tutor.yaml").read_text()
    )["software"]
    with pytest.raises(PreflightError):
        map_final_tutor(software, {})
