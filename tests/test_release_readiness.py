"""Regression gates for the final-burst release contract."""

import copy
import json
import math
import time
from unittest.mock import patch

import pytest
import yaml

from src.common.candidate import Candidate, ROOT, baseline_candidate
from src.common.errors import ConfigError, MetricsError, OptimizerError, RuntimeExecutionError
from src.common.security import digest
from src.hardware.energy_estimator import read_energy_uj
from src.orchestration.dispatch import FUNCTIONS
from src.orchestration.experiment import run_experiment
from src.orchestration.nodes.evaluation import verify_results
from src.orchestration.nodes.shared import execute_runtime
from src.orchestration.nodes.validation import mapping_node, validation_node
from src.tutor.evaluator import evaluate_required_concepts, load_evaluation_set


def _software(config, runtime, context):
    return {
        "candidate_id": Candidate.from_dict(config).candidate_id,
        "status": "completed",
        "software": config["software"],
        "metrics": {"latency_ms": 10.0, "throughput_qps": 1.0, "sample_count": 3, "answer_quality": 0.75, "question_count": 3},
        "dataset": {
            "dataset_id": "openstax-college-physics-2e-ch4-concepts-v1",
            "source_url": "https://openstax.org/books/college-physics-2e/pages/4-conceptual-questions",
            "license": "CC BY-NC-SA 4.0",
            "reference_visible_to_model": False,
        },
        "provenance": {"model_sha256": "a" * 64},
    }


def _hardware(config, runtime, context):
    return {
        "candidate_id": Candidate.from_dict(config).candidate_id,
        "status": "completed",
        "hardware": config["hardware"],
        "metrics": {"simulated_seconds": 0.01, "sim_ticks": 10, "instructions": 10, "cycles_per_core": [10, 10], "ipc_per_core": [1.0, 1.0], "l1d_miss_rate_per_core": [0.1, 0.1], "l2_miss_rate": 0.1},
        "correctness": {"status": "PASS", "max_absolute_error": 0.01, "mean_squared_error": 0.001},
        "provenance": {"resolved_config_verified": True, "correctness_tolerance": {"max_absolute_error": 0.1, "mean_squared_error": 0.01}},
    }


def _energy(config, hardware, runtime, context):
    return {
        "candidate_id": Candidate.from_dict(config).candidate_id,
        "status": "completed",
        "hardware_result_id": digest(hardware),
        "metrics": {"estimated_cache_dynamic_energy_uj": 5.0},
        "provenance": {"estimator": "fixture"},
    }


def test_real_openstax_metadata_is_accepted():
    dataset = load_evaluation_set()
    assert dataset["dataset_id"] == "openstax-college-physics-2e-ch4-concepts-v1"
    assert dataset["license"] == "CC BY-NC-SA 4.0" and len(dataset["items"]) == 3


def test_production_proxy_accepted_and_old_proxy_rejected():
    assert Candidate.from_dict(baseline_candidate()).config["workload"] == {
        "context_tokens": 512, "query_heads": 14, "kv_heads": 2, "head_dimension": 64, "layers": 1
    }
    old = baseline_candidate()
    old["workload"].update(query_heads=4, kv_heads=2, head_dimension=32)
    with pytest.raises(ConfigError):
        Candidate.from_dict(old)


def test_numeric_candidate_identity_is_canonical():
    integer = baseline_candidate()
    integer["software"]["temperature"] = 0
    floating = baseline_candidate()
    floating["software"]["temperature"] = 0.0
    assert Candidate.from_dict(integer).candidate_id == Candidate.from_dict(floating).candidate_id


def test_campaign_deadline_is_propagated_as_effective_timeout():
    context = {"run_id": "deadline", "candidate_id": Candidate.from_dict(baseline_candidate()).candidate_id}
    mapped = mapping_node(validation_node(baseline_candidate(), context), context)
    observed = {}
    def runner(config, runtime, context):
        observed.update(runtime)
        return {"ok": True}
    result = execute_runtime("software", mapped, {"timeout_seconds": 100, "deadline_epoch_seconds": time.time() + 0.2, "retries": 0}, context, runner)
    assert result["event"]["status"] == "completed"
    assert 0 < observed["timeout_seconds"] <= 0.21
    assert "deadline_epoch_seconds" in observed


@pytest.mark.parametrize("outcome,counter", [("malformed", "malformed_responses"), ("duplicate", "duplicates")])
def test_billed_rejected_gemini_calls_are_accounted(tmp_path, outcome, counter):
    from src.orchestration.chia import chia_entrypoint
    metadata = {"outcome": outcome, "usage": {"input_tokens": 2, "candidate_tokens": 1, "thought_tokens": 0, "output_tokens": 1, "total_tokens": 3}, "estimated_cost_usd": 0.001}
    error = OptimizerError("rejected")
    error.optimizer_metadata = metadata
    with (
        patch("src.orchestration.gemini_api.GeminiAPIOptimizer") as cls,
        patch("src.orchestration.nodes.software.run_software_candidate", side_effect=_software),
        patch("src.orchestration.nodes.hardware.run_gem5_candidate", side_effect=_hardware),
        patch("src.orchestration.nodes.energy.run_energy_candidate", side_effect=_energy),
    ):
        cls.return_value.timeout_seconds = 60
        cls.return_value.propose.side_effect = error
        result = chia_entrypoint({"campaign_id": f"gemini-{outcome}", "iterations": 1, "results_root": str(tmp_path), "optimizer": {"enabled": True, "policy": "gemini_api", "model": "gemini-3.1-flash-lite", "max_calls": 1, "budget_usd": 1.0, "timeout_seconds": 60}})
    ledger = result["gemini_usage_total"]
    assert ledger["request_count"] == 1 and ledger["rejected_proposals"] == 1
    assert ledger[counter] == 1 and ledger["total_tokens"] == 3


def test_gemini_request_failure_is_counted_without_fabricated_tokens(tmp_path):
    from src.orchestration.chia import chia_entrypoint
    error = OptimizerError("request failed")
    error.optimizer_metadata = {"outcome": "request_failure", "usage": None, "estimated_cost_usd": None}
    with (
        patch("src.orchestration.gemini_api.GeminiAPIOptimizer") as cls,
        patch("src.orchestration.nodes.software.run_software_candidate", side_effect=_software),
        patch("src.orchestration.nodes.hardware.run_gem5_candidate", side_effect=_hardware),
        patch("src.orchestration.nodes.energy.run_energy_candidate", side_effect=_energy),
    ):
        cls.return_value.timeout_seconds = 60
        cls.return_value.propose.side_effect = error
        result = chia_entrypoint({"campaign_id": "gemini-request-failure", "iterations": 1, "results_root": str(tmp_path), "optimizer": {"enabled": True, "policy": "gemini_api", "model": "gemini-3.1-flash-lite", "max_calls": 1, "budget_usd": 1.0, "timeout_seconds": 60}})
    ledger = result["gemini_usage_total"]
    assert ledger["request_count"] == 1 and ledger["unmetered_request_failures"] == 1
    assert ledger["total_tokens"] == 0 and ledger["estimated_cost_usd"] == 0


def test_single_writer_prevents_delayed_worker_overwrite(tmp_path):
    assert "record" not in FUNCTIONS
    with (
        patch("src.orchestration.nodes.software.run_software_candidate", side_effect=_software),
        patch("src.orchestration.nodes.hardware.run_gem5_candidate", side_effect=_hardware),
        patch("src.orchestration.nodes.energy.run_energy_candidate", side_effect=_energy),
        patch("src.orchestration.experiment.persist_record", wraps=__import__("src.common.records", fromlist=["persist_record"]).persist_record) as writer,
    ):
        record = run_experiment(baseline_candidate(), results_root=tmp_path)
    assert record["status"] == "completed" and writer.call_count == 1


def test_wrong_energy_join_and_nonfinite_energy_are_rejected():
    config = baseline_candidate()
    cid = Candidate.from_dict(config).candidate_id
    sw, hw = _software(config, {}, {}), _hardware(config, {}, {})
    en = _energy(config, hw, {}, {})
    forged = copy.deepcopy(en)
    forged["hardware_result_id"] = "0" * 64
    with pytest.raises(MetricsError, match="stale"):
        verify_results(config, cid, sw, hw, forged)
    en["metrics"]["estimated_cache_dynamic_energy_uj"] = math.nan
    with pytest.raises(MetricsError, match="Energy estimate"):
        verify_results(config, cid, sw, hw, en)


def test_nonfinite_energy_file_rejected(tmp_path):
    path = tmp_path / "energy.yaml"
    path.write_text(yaml.safe_dump({"energy_estimation": {"Total": float("nan"), "components": []}}), encoding="utf-8")
    with pytest.raises(Exception, match="nonfinite"):
        read_energy_uj(path)


def test_all_failed_search_returns_incomplete_state(tmp_path):
    from src.orchestration.chia import chia_entrypoint
    with patch("src.orchestration.nodes.software.run_software_candidate", side_effect=RuntimeExecutionError("down")):
        result = chia_entrypoint({"campaign_id": "all-failed", "iterations": 1, "results_root": str(tmp_path)})
    assert result["state"] == "incomplete" and result["experiments"][0]["status"] == "failed"


def test_random_and_gemini_share_the_same_graph_executor():
    source = (ROOT / "src/orchestration/chia.py").read_text(encoding="utf-8")
    assert source.count("record = run_experiment(") == 1
    assert "RandomProposer" in source and "GeminiAPIOptimizer" in source

    from src.orchestration.random_search import RandomProposer
    candidate, metadata = RandomProposer(seed=7).propose([], set())
    assert Candidate.from_dict(candidate).candidate_id
    assert metadata == {"seed": 7, "request_count": 0}


def test_quality_matching_uses_word_boundaries():
    result = evaluate_required_concepts("An earthquake occurred.", [["earth"]])
    assert result["score"] == 0
