"""Integration-owned deterministic contract/graph tests with mocked runtime boundaries."""

import copy
import json
from unittest.mock import patch
import pytest
from src.common.candidate import Candidate, baseline_candidate
from src.common.errors import (
    ConfigError,
    TransientRuntimeError,
    RuntimeExecutionError,
    MetricsError,
)
from src.common.security import safe_id, within, strict_json, local_endpoint
from src.orchestration.chia import chia_entrypoint, validate_campaign_config
from src.orchestration.experiment import run_experiment
from src.orchestration.nodes.validation import validation_node, mapping_node
from src.orchestration.nodes.shared import execute_runtime
from src.common.records import validate_record
from src.hardware.runner import parse_correctness
from src.tutor.metrics import extract_generation_metrics


def software(config, runtime, context):
    return {
        "candidate_id": Candidate.from_dict(config).candidate_id,
        "status": "completed",
        "software": config["software"],
        "metrics": {
            "latency_ms": 10.0,
            "throughput_qps": 100.0,
            "sample_count": config["measurement"]["software_repetitions"],
        },
        "provenance": {"runtime_version": "test-only", "model_digest": "fixture"},
    }


def hardware(config, runtime, context):
    return {
        "candidate_id": Candidate.from_dict(config).candidate_id,
        "status": "completed",
        "hardware": config["hardware"],
        "metrics": {
            "simulated_seconds": 0.01,
            "sim_ticks": 10000000000,
            "instructions": 100,
            "cycles_per_core": [10, 10],
            "ipc_per_core": [1.0, 1.0],
            "l1d_miss_rate_per_core": [0.1, 0.2],
            "l2_miss_rate": 0.3,
        },
        "correctness": {
            "status": "PASS",
            "max_absolute_error": 0.01,
            "mean_squared_error": 0.0001,
        },
        "provenance": {
            "resolved_config_verified": True,
            "gem5_version": "fixture",
            "correctness_tolerance": {
                "max_absolute_error": 0.1,
                "mean_squared_error": 0.01,
            },
        },
    }


@pytest.fixture
def mocked_runtimes():
    with (
        patch(
            "src.orchestration.nodes.software.run_software_candidate",
            side_effect=software,
        ) as sw,
        patch(
            "src.orchestration.nodes.hardware.run_gem5_candidate", side_effect=hardware
        ) as hw,
    ):
        yield sw, hw


def test_three_candidate_full_loop(tmp_path, mocked_runtimes):
    result = chia_entrypoint({"campaign_id": "three", "results_root": str(tmp_path)})
    assert result["state"] == "completed"
    assert result["stop_reason"] == "iteration_limit"
    assert len(result["experiments"]) == 3
    assert len({r["candidate_id"] for r in result["experiments"]}) == 3
    for record in result["experiments"]:
        validate_record(record)
        saved = json.loads(
            (tmp_path / "three" / f"{record['run_id']}.json").read_text()
        )
        assert saved["candidate"]["software"] == saved["software_result"]["software"]
        assert saved["candidate"]["hardware"] == saved["hardware_result"]["hardware"]
        assert {e["node"] for e in saved["events"]} == {
            "validation",
            "mapping",
            "software",
            "hardware",
            "evaluation",
            "record",
        }


@pytest.mark.parametrize(
    "config",
    [
        {"runtime": None},
        {"runtime": {"software": "bad"}},
        {"runtime": {"software": {"endpoint": "[http://127.0.0.1:11434](http://127.0.0.1:11434)"}}},
        {"runtime": {"hardware": {"correctness_tolerance": {"max_absolute_error": 0.01}}}},
        {"software": {"endpoint": "http://127.0.0.1:11434"}},
    ],
)
def test_campaign_validation_rejects_malformed_operator_config(config):
    with pytest.raises(ConfigError):
        validate_campaign_config(config)


def test_campaign_validation_accepts_reviewed_chia_runtime():
    checked = validate_campaign_config(
        {
            "campaign_id": "acceptance",
            "mode": "chia",
            "tier": "integration",
            "backend": "contabo",
            "iterations": 1,
            "runtime": {
                "software": {"endpoint": "http://127.0.0.1:11434"},
                "hardware": {
                    "correctness_tolerance": {
                        "max_absolute_error": 0.01,
                        "mean_squared_error": 0.00001,
                    }
                },
            },
        }
    )
    assert checked["mode"] == "chia" and checked["iterations"] == 1


def test_invalid_candidate_never_executes_and_is_recorded(tmp_path, mocked_runtimes):
    config = baseline_candidate()
    config["hardware"]["frequency_ghz"] = 99
    result = run_experiment(config, results_root=tmp_path)
    assert result["status"] == "rejected" and result["candidate"] is None
    assert not mocked_runtimes[0].called and not mocked_runtimes[1].called
    validate_record(result)


def test_failed_node_preserves_other_result(tmp_path, mocked_runtimes):
    mocked_runtimes[1].side_effect = RuntimeExecutionError(
        "Hardware compilation failed."
    )
    result = run_experiment(baseline_candidate(), results_root=tmp_path)
    assert result["status"] == "failed" and result["software_result"] is not None
    assert result["failure"]["stage"] == "hardware"
    validate_record(result)


def test_duplicate_is_not_executed(tmp_path, mocked_runtimes):
    c = baseline_candidate()
    result = chia_entrypoint(
        {
            "campaign_id": "dup",
            "results_root": str(tmp_path),
            "candidates": [c, copy.deepcopy(c)],
        }
    )
    assert (
        len(result["experiments"]) == 1
        and result["skipped"][0]["reason"] == "duplicate_candidate"
    )
    assert mocked_runtimes[0].call_count == 1


def test_candidate_is_immutable_snapshot():
    data = baseline_candidate()
    c = Candidate.from_dict(data)
    before = c.candidate_id
    data["hardware"]["issue_width"] = 4
    c.config["hardware"]["issue_width"] = 1
    assert c.candidate_id == before and c.config["hardware"]["issue_width"] == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["hardware"].update(extra=1),
        lambda c: c["software"].update(temperature=True),
        lambda c: c["software"].update(temperature=float("nan")),
        lambda c: c["software"].update(model="other"),
        lambda c: c["hardware"].update(cpu_model="RiscvTimingSimpleCPU", issue_width=2),
        lambda c: c["workload"].update(query_heads=8),
        lambda c: c.update(api_key="secret"),
    ],
)
def test_invalid_knob_constraints(mutate):
    c = baseline_candidate()
    mutate(c)
    with pytest.raises(ValueError):
        Candidate.from_dict(c)


@pytest.mark.parametrize("value", ["..", "../x", "a/b", "x;whoami", ""])
def test_safe_identifiers(value):
    with pytest.raises(ConfigError):
        safe_id(value)


def test_paths_and_http_boundaries(tmp_path):
    with pytest.raises(ConfigError):
        within(tmp_path, "../escape")
    for url in (
        "https://example.com",
        "http://127.0.0.1@evil.test",
        "http://localhost/path",
        "http://localhost?token=x",
    ):
        with pytest.raises(ConfigError):
            local_endpoint(url)


@pytest.mark.parametrize(
    "text", ['{"a":1,"a":2}', '{"x":NaN}', "```json\n{}\n```", "{} trailing"]
)
def test_strict_json(text):
    with pytest.raises(ConfigError):
        strict_json(text)


def test_retry_only_transient():
    context = {
        "run_id": "test",
        "candidate_id": Candidate.from_dict(baseline_candidate()).candidate_id,
    }
    mapped = mapping_node(validation_node(baseline_candidate(), context), context)
    with (
        patch("src.orchestration.nodes.shared.time.sleep"),
        patch(
            "tests.test_full_loop.software",
            side_effect=[TransientRuntimeError("Temporary."), {"ok": True}],
        ) as runner,
    ):
        result = execute_runtime(
            "software", mapped, {"timeout_seconds": 10, "retries": 1}, context, runner
        )
    assert len(result["events"]) == 2 and result["event"]["status"] == "completed"
    with patch(
        "tests.test_full_loop.software",
        side_effect=RuntimeExecutionError("Build failed."),
    ) as runner:
        result = execute_runtime(
            "hardware", mapped, {"timeout_seconds": 10, "retries": 2}, context, runner
        )
    assert runner.call_count == 1 and result["event"]["status"] == "failed"


def test_finite_but_inaccurate_is_rejected():
    with pytest.raises(MetricsError):
        parse_correctness(
            "status=PASS\nmax_absolute_error=100\nmean_squared_error=100",
            {"max_absolute_error": 0.1, "mean_squared_error": 0.1},
        )


def test_missing_metrics_are_not_zero():
    with pytest.raises(MetricsError):
        extract_generation_metrics({"done": True, "response": "answer"})


def test_completed_record_detects_forged_metrics(tmp_path, mocked_runtimes):
    record = run_experiment(baseline_candidate(), results_root=tmp_path)
    record["software_result"]["metrics"]["latency_ms"] = float("nan")
    with pytest.raises((ConfigError, MetricsError)):
        validate_record(record)


def test_runtime_deadline_does_not_retry_timeout():
    from src.common.errors import ExecutionTimeout

    context = {"run_id": "timeout"}
    mapped = mapping_node(validation_node(baseline_candidate(), context), context)
    with patch(
        "tests.test_full_loop.software", side_effect=ExecutionTimeout("Timed out.")
    ) as runner:
        result = execute_runtime(
            "software", mapped, {"timeout_seconds": 10, "retries": 2}, context, runner
        )
    assert runner.call_count == 1
    assert result["event"]["status"] == "failed"


def test_nonfinite_runtime_data_still_produces_failed_record(tmp_path, mocked_runtimes):
    def bad(config, runtime, context):
        value = hardware(config, runtime, context)
        value["metrics"]["simulated_seconds"] = float("nan")
        return value

    mocked_runtimes[1].side_effect = bad
    record = run_experiment(baseline_candidate(), results_root=tmp_path)
    assert record["status"] == "failed"
    assert record["hardware_result"] is None
    validate_record(record)
def test_metered_gemini_candidate_is_saved(
    tmp_path,
    mocked_runtimes,
):
    metadata = {
        "model": "gemini-3.1-flash-lite",
        "sdk": "google-genai",
        "prompt_version": "candidate-json-v2",
        "prompt_sha256": "a" * 64,
        "usage": {
            "input_tokens": 422,
            "candidate_tokens": 221,
            "thought_tokens": 0,
            "output_tokens": 221,
            "total_tokens": 643,
        },
        "estimated_cost_usd": 0.000437,
    }

    with patch(
        "src.orchestration.gemini_api.GeminiAPIOptimizer"
    ) as optimizer_class:
        optimizer_class.return_value.timeout_seconds = 60

        optimizer_class.return_value.propose.return_value = (
            baseline_candidate(),
            metadata,
        )

        result = chia_entrypoint(
            {
                "campaign_id": "gemini-metered",
                "iterations": 1,
                "results_root": str(tmp_path),
                "optimizer": {
                    "enabled": True,
	                    "policy": "gemini_api",
                    "model": "gemini-3.1-flash-lite",
                    "max_calls": 1,
                    "budget_usd": 10.0,
                    "timeout_seconds": 60,
                },
            }
        )

    assert result["state"] == "completed"
    assert result["optimizer_calls"] == 1

    assert (
        result["gemini_usage_total"]["total_tokens"]
        == 643
    )

    assert result["gemini_usage_total"][
        "estimated_cost_usd"
    ] == pytest.approx(0.000437)

    record = result["experiments"][0]

    assert record["optimizer"]["policy"] == "gemini_api"
    assert record["optimizer"]["metadata"] == metadata

    summary_path = (
        tmp_path
        / "gemini-metered"
        / "summary.json"
    )

    saved_summary = json.loads(
        summary_path.read_text(encoding="utf-8")
    )

    assert saved_summary[
        "gemini_usage_total"
    ]["input_tokens"] == 422
