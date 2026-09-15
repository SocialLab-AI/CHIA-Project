import json
from unittest.mock import call, patch

import pytest

from src.orchestration.chia import chia_entrypoint
from src.orchestration.nodes.optimizer import _parse_json_response


def test_parse_optimizer_json_response():
    response = """
    {
        "hardware": {
            "cpu_model": "RiscvO3CPU",
            "cores": 2,
            "issue_width": 2
        }
    }
    """

    result = _parse_json_response(response)

    assert result["cpu_model"] == "RiscvO3CPU"
    assert result["cores"] == 2
    assert result["issue_width"] == 2


def test_parse_optimizer_response_rejects_missing_json():
    with pytest.raises(ValueError):
        _parse_json_response("No configuration was produced.")


def test_chia_entrypoint_runs_hardware_only_iterations(tmp_path):
    candidates = [
        {
            "cpu_model": "RiscvO3CPU",
            "cores": 2,
            "issue_width": 1,
        },
        {
            "cpu_model": "RiscvO3CPU",
            "cores": 2,
            "issue_width": 2,
        },
    ]

    hardware_results = [
        {
            "run_id": "run-1",
            "status": {"state": "completed"},
            "hardware": candidates[0],
            "metrics": {"latency_ms": 20.0},
        },
        {
            "run_id": "run-2",
            "status": {"state": "completed"},
            "hardware": candidates[1],
            "metrics": {"latency_ms": 18.0},
        },
    ]

    config = {
        "design_space": {
            "active_candidates": {
                "hardware": {
                    "issue_width": [1, 2],
                }
            }
        },
        "iterations": 2,
        "optimizer_model": "test-model",
        "campaign_id": "test-campaign",
        "results_root": str(tmp_path),
    }

    with patch(
        "src.orchestration.chia.propose_hardware_candidate",
        side_effect=candidates,
    ) as mock_optimizer, patch(
        "src.orchestration.chia.run_gem5_candidate",
    ) as mock_hardware, patch(
        "src.orchestration.chia.get",
        side_effect=hardware_results,
    ) as mock_get:

        mock_hardware.chia_remote.side_effect = [
            "result-reference-1",
            "result-reference-2",
        ]

        result = chia_entrypoint(config)

    assert result["status"] == "completed"
    assert result["mode"] == "hardware_only"
    assert result["campaign_id"] == "test-campaign"
    assert result["iterations"] == 2
    assert len(result["experiments"]) == 2
    assert len(result["history"]) == 2

    assert result["experiments"][0]["candidate"] == candidates[0]
    assert (
        result["experiments"][1]["hardware_result"]
        == hardware_results[1]
    )

    assert mock_optimizer.call_count == 2
    assert mock_hardware.chia_remote.call_args_list == [
        call(candidates[0]),
        call(candidates[1]),
    ]
    assert mock_get.call_args_list == [
        call("result-reference-1"),
        call("result-reference-2"),
    ]

    campaign_directory = tmp_path / "test-campaign"
    iteration_1 = campaign_directory / "iteration-001.json"
    iteration_2 = campaign_directory / "iteration-002.json"
    summary_path = campaign_directory / "summary.json"

    assert iteration_1.exists()
    assert iteration_2.exists()
    assert summary_path.exists()

    saved_iteration = json.loads(
        iteration_1.read_text(encoding="utf-8")
    )
    saved_summary = json.loads(
        summary_path.read_text(encoding="utf-8")
    )

    assert saved_iteration["candidate"] == candidates[0]
    assert (
        saved_iteration["hardware_result"]["metrics"]["latency_ms"]
        == 20.0
    )
    assert saved_summary["state"] == "completed"
    assert saved_summary["completed_iterations"] == 2
    assert len(saved_summary["experiments"]) == 2


def test_chia_entrypoint_rejects_zero_iterations():
    config = {
        "design_space": {},
        "iterations": 0,
    }

    with pytest.raises(ValueError, match="iterations must be at least 1"):
        chia_entrypoint(config)
