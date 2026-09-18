import json

import pytest

import scripts.run_gemini_software_search as software_search
from src.common.candidate import Candidate, baseline_candidate
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


def test_integer_zero_temperature_has_stable_candidate_id():
    integer_zero = parse_software_proposal(
        json.dumps(
            {
                "software": {
                    "temperature": 0,
                    "max_output_tokens": 128,
                }
            }
        ),
        software_repetitions=2,
    )
    float_zero = parse_software_proposal(
        json.dumps(
            {
                "software": {
                    "temperature": 0.0,
                    "max_output_tokens": 128,
                }
            }
        ),
        software_repetitions=2,
    )

    assert Candidate.from_dict(integer_zero).candidate_id == (
        Candidate.from_dict(float_zero).candidate_id
    )


def _history_record(*, temperature, tokens, quality, latency):
    candidate = baseline_candidate()
    candidate["measurement"]["software_repetitions"] = 2
    candidate["software"]["temperature"] = temperature
    candidate["software"]["max_output_tokens"] = tokens
    candidate_id = Candidate.from_dict(candidate).candidate_id
    return {
        "candidate_id": candidate_id,
        "status": "completed",
        "software": candidate["software"],
        "metrics": {
            "answer_quality": quality,
            "latency_ms": latency,
            "mean_latency_ms": latency + 100,
            "p95_latency_ms": latency + 500,
            "throughput_qps": 1000 / (latency + 100),
        },
    }


def test_history_summary_loads_valid_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(software_search, "ROOT", tmp_path)
    record = _history_record(
        temperature=0.2,
        tokens=256,
        quality=0.8,
        latency=3500,
    )
    path = tmp_path / "summary.json"
    path.write_text(
        json.dumps(
            {
                "scope": "software_only",
                "repetitions_per_question": 2,
                "records": [record],
            }
        ),
        encoding="utf-8",
    )

    loaded = software_search.load_history_summary(path, 2)

    assert loaded["path"] == "summary.json"
    assert record["candidate_id"] in loaded["seen"]
    assert loaded["history"][0]["source"] == "history_summary"


def test_integer_zero_history_blocks_float_equivalent(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(software_search, "ROOT", tmp_path)
    record = _history_record(
        temperature=0,
        tokens=128,
        quality=0.77,
        latency=3560,
    )
    path = tmp_path / "summary.json"
    path.write_text(
        json.dumps(
            {
                "scope": "software_only",
                "repetitions_per_question": 2,
                "records": [record],
            }
        ),
        encoding="utf-8",
    )

    loaded = software_search.load_history_summary(path, 2)
    equivalent = baseline_candidate()
    equivalent["measurement"]["software_repetitions"] = 2
    equivalent["software"]["temperature"] = 0.0
    equivalent["software"]["max_output_tokens"] = 128
    equivalent_id = Candidate.from_dict(equivalent).candidate_id

    assert record["candidate_id"] in loaded["seen"]
    assert equivalent_id in loaded["seen"]


def test_history_summary_rejects_repetition_mismatch(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(software_search, "ROOT", tmp_path)
    path = tmp_path / "summary.json"
    path.write_text(
        json.dumps(
            {
                "scope": "software_only",
                "repetitions_per_question": 1,
                "records": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="same repetitions"):
        software_search.load_history_summary(path, 2)


def test_history_summary_rejects_forged_candidate_id(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(software_search, "ROOT", tmp_path)
    record = _history_record(
        temperature=0.2,
        tokens=256,
        quality=0.8,
        latency=3500,
    )
    record["candidate_id"] = "0" * 64
    path = tmp_path / "summary.json"
    path.write_text(
        json.dumps(
            {
                "scope": "software_only",
                "repetitions_per_question": 2,
                "records": [record],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="candidate ID"):
        software_search.load_history_summary(path, 2)


def test_comparison_summary_reports_best_and_pareto_candidates():
    faster = _history_record(
        temperature=0.0,
        tokens=128,
        quality=0.75,
        latency=3000,
    )
    higher_quality = _history_record(
        temperature=0.2,
        tokens=256,
        quality=0.8,
        latency=3500,
    )
    dominated = _history_record(
        temperature=0.5,
        tokens=128,
        quality=0.7,
        latency=4000,
    )

    comparison = software_search.comparison_summary(
        [faster, higher_quality, dominated]
    )

    assert comparison["completed_candidate_count"] == 3
    assert comparison["best_by"]["answer_quality"]["candidate_id"] == (
        higher_quality["candidate_id"]
    )
    assert comparison["best_by"]["median_latency_ms"]["candidate_id"] == (
        faster["candidate_id"]
    )
    assert set(comparison["pareto_candidate_ids"]) == {
        faster["candidate_id"],
        higher_quality["candidate_id"],
    }
