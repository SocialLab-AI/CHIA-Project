"""Regression gates for the final-burst release contract."""

import copy
import json
import math
import sys
import time
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import yaml

from src.common.candidate import Candidate, ROOT, baseline_candidate
from src.common.errors import ConfigError, MetricsError, OptimizerError, RuntimeExecutionError
from src.common.security import digest
from src.hardware.energy_estimator import read_energy_uj
from src.hardware.energy_mapping import ENERGY_SCOPE
from src.orchestration.dispatch import FUNCTIONS, RESOURCES
from src.orchestration.experiment import run_experiment
from src.orchestration.nodes.evaluation import verify_results
from src.orchestration.nodes.shared import execute_runtime
from src.orchestration.nodes.validation import mapping_node, validation_node
from src.tutor.evaluator import (
    evaluate_exact_option_text,
    evaluate_required_concepts,
    load_evaluation_set,
)


def _software(config, runtime, context):
    return {
        "candidate_id": Candidate.from_dict(config).candidate_id,
        "status": "completed",
        "software": config["software"],
        "metrics": {"latency_ms": 10.0, "throughput_qps": 1.0, "sample_count": 250 * config["measurement"]["software_repetitions"], "answer_quality": 0.75, "question_count": 250, "quality_method": "exact_option_text_accuracy"},
        "dataset": {
            "dataset_id": "openstax-aligned-team-assessment-250-v1",
            "source_url": "https://openstax.org/",
            "license": "Team-authored evaluation material; repository use authorized by contributor",
            "reference_visible_to_model": False,
            "quality_method": "exact_option_text_accuracy",
            "questions_sha256": "c" * 64,
            "references_sha256": "d" * 64,
            "source_description": "Team-authored original wording aligned to OpenStax topic scope.",
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
        "provenance": {"resolved_config_verified": True, "stats_sha256": "b" * 64, "correctness_tolerance": {"max_absolute_error": 0.1, "mean_squared_error": 0.01}},
    }


def _energy(config, hardware, runtime, context):
    return {
        "candidate_id": Candidate.from_dict(config).candidate_id,
        "status": "completed",
        "hardware_result_id": digest(hardware),
        "stats_sha256": "b" * 64,
        "metrics": {"estimated_cache_dynamic_energy_uj": 5.0},
        "scope": ENERGY_SCOPE,
        "components": [
            {"name": name, "energy": 1.0}
            for name in (
                "cpu0_l1i", "cpu0_l1d", "cpu1_l1i", "cpu1_l1d", "shared_l2"
            )
        ],
        "provenance": {
            "estimator": "fixture",
            "container_image_digest": "sha256:" + "a" * 64,
            "accelergy_version": "0.3",
            "accelergy_commit": "a" * 40,
            "mcpat_version": "1.3",
            "mcpat_commit": "b" * 40,
            "plugin_commit": "c" * 40,
            "mapping_sha256": "d" * 64,
            "architecture_sha256": "e" * 64,
            "action_counts_sha256": "f" * 64,
            "energy_result_sha256": "1" * 64,
            "execution_duration_seconds": 1.0,
            "energy_scope": ENERGY_SCOPE,
        },
    }


def _combined_hardware(config, runtime, context):
    result = _hardware(config, runtime, context)
    evidence = _energy(config, result, runtime.get("energy", {}), context)
    energy_uj = evidence["metrics"]["estimated_cache_dynamic_energy_uj"]
    result["metrics"].update(
        energy_uj=energy_uj,
        estimated_cache_dynamic_energy_uj=energy_uj,
        energy_scope=evidence["scope"],
    )
    result["provenance"]["gem5_result_sha256"] = evidence[
        "hardware_result_id"
    ]
    result["energy_evidence"] = evidence
    return result


def test_real_team_assessment_metadata_is_accepted():
    dataset = load_evaluation_set()
    assert dataset["dataset_id"] == "openstax-aligned-team-assessment-250-v1"
    assert dataset["method"] == "exact_option_text_accuracy"
    assert len(dataset["items"]) == 250
    assert all(len(item["question"]["options"]) == 4 for item in dataset["items"])
    positions = [
        item["question"]["options"].index(item["reference"]["correct_answer"])
        for item in dataset["items"]
    ]
    assert [positions.count(index) for index in range(4)] == [63, 63, 62, 62]
    public_questions = json.loads(
        (ROOT / "data/questions/questions.json").read_text(encoding="utf-8")
    )
    assert all(
        "correct_answer" not in question and isinstance(question["options"], list)
        for question in public_questions["questions"]
    )


def test_committed_evidence_checksums_are_current():
    from scripts.verify_evidence_checksums import audit_evidence

    result = audit_evidence()
    assert result["status"] == "passed", result["failures"]
    assert result["verified_files"] == 36
    assert result["external_files"] == 4


def test_final_campaign_pins_the_runtime_verified_qwen_artifact():
    campaign = yaml.safe_load(
        (ROOT / "experiment-contracts/campaigns/final-burst.yaml").read_text(
            encoding="utf-8"
        )
    )
    software = campaign["runtime"]["software"]
    assert software["assets_root"] == "/opt/chia/models"
    assert software["gguf"] == "qwen2.5-0.5b-instruct-q5_k_m.gguf"
    assert software["model_sha256"] == (
        "041474553fcabfc2a2d67903f9d2c2e50bd92528e670da4f33b5d0ce6e59fd55"
    )
    assert campaign["runtime"]["energy"]["image"] == (
        "chia-energy-tools:0.3"
    )


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
        patch(
            "src.orchestration.nodes.hardware.run_gem5_candidate",
            side_effect=_combined_hardware,
        ),
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
        patch(
            "src.orchestration.nodes.hardware.run_gem5_candidate",
            side_effect=_combined_hardware,
        ),
    ):
        cls.return_value.timeout_seconds = 60
        cls.return_value.propose.side_effect = error
        result = chia_entrypoint({"campaign_id": "gemini-request-failure", "iterations": 1, "results_root": str(tmp_path), "optimizer": {"enabled": True, "policy": "gemini_api", "model": "gemini-3.1-flash-lite", "max_calls": 1, "budget_usd": 1.0, "timeout_seconds": 60}})
    ledger = result["gemini_usage_total"]
    assert ledger["request_count"] == 1 and ledger["unmetered_request_failures"] == 1
    assert ledger["total_tokens"] == 0 and ledger["estimated_cost_usd"] == 0


def test_single_writer_prevents_delayed_worker_overwrite(tmp_path):
    assert "record" not in FUNCTIONS
    assert "energy" not in FUNCTIONS
    assert "energy" not in RESOURCES
    with (
        patch("src.orchestration.nodes.software.run_software_candidate", side_effect=_software),
        patch(
            "src.orchestration.nodes.hardware.run_gem5_candidate",
            side_effect=_combined_hardware,
        ),
        patch("src.orchestration.experiment.persist_record", wraps=__import__("src.common.records", fromlist=["persist_record"]).persist_record) as writer,
    ):
        record = run_experiment(baseline_candidate(), results_root=tmp_path)
    assert record["status"] == "completed" and writer.call_count == 1


def test_wrong_energy_join_and_nonfinite_energy_are_rejected():
    config = baseline_candidate()
    cid = Candidate.from_dict(config).candidate_id
    sw, hw = _software(config, {}, {}), _combined_hardware(config, {}, {})
    en = hw["energy_evidence"]
    forged = copy.deepcopy(en)
    forged["hardware_result_id"] = "0" * 64
    with pytest.raises(MetricsError, match="stale"):
        verify_results(config, cid, sw, hw, forged)
    en["metrics"]["estimated_cache_dynamic_energy_uj"] = math.nan
    with pytest.raises(MetricsError, match="Energy estimate"):
        verify_results(config, cid, sw, hw, en)


def test_evaluation_rejects_hardware_without_energy_evidence():
    config = baseline_candidate()
    candidate_id = Candidate.from_dict(config).candidate_id
    with pytest.raises(MetricsError, match="Energy result"):
        verify_results(
            config,
            candidate_id,
            _software(config, {}, {}),
            _hardware(config, {}, {}),
        )


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


def test_gemini_optimizer_declares_all_four_pareto_objectives():
    from src.orchestration.gemini_api import (
        PARETO_OBJECTIVES,
        PROMPT_VERSION,
    )

    assert PARETO_OBJECTIVES == (
        "native_latency_ms",
        "proxy_simulated_seconds",
        "estimated_cache_dynamic_energy_uj",
        "answer_quality_loss",
    )
    assert PROMPT_VERSION == "candidate-json-v3-four-objective-pareto"


def test_quality_matching_uses_word_boundaries():
    result = evaluate_required_concepts("An earthquake occurred.", [["earth"]])
    assert result["score"] == 0


def test_exact_option_text_accuracy_rejects_labels_and_extra_words():
    options = ["Conservation of mass", "Boyle's law", "Avogadro's law", "Energy"]
    assert evaluate_exact_option_text(
        "Conservation of mass", options, "Conservation of mass"
    )["score"] == 1.0
    assert evaluate_exact_option_text(
        "Answer: Conservation of mass", options, "Conservation of mass"
    )["score"] == 1.0
    assert evaluate_exact_option_text(
        "B", options, "Conservation of mass"
    )["score"] == 0.0
    assert evaluate_exact_option_text(
        "Conservation of mass because atoms are conserved.",
        options,
        "Conservation of mass",
    )["score"] == 0.0


@pytest.mark.parametrize("cli_args,expected_budget", [(["--smoke"], 1), (["--method", "random"], 3)])
def test_cli_profiles_keep_execution_and_stopping_budgets_equal(cli_args, expected_budget):
    from scripts.run_experiment import main

    campaign = ROOT / "experiment-contracts/campaigns/final-burst.yaml"
    with patch.object(sys, "argv", ["run_experiment.py", "--config", str(campaign), *cli_args]), patch(
        "scripts.run_experiment.chia_entrypoint",
        return_value={"state": "completed", "experiments": []},
    ) as entrypoint:
        assert main() == 0

    effective = entrypoint.call_args.args[0]
    assert effective["iterations"] == expected_budget
    assert effective["stopping"]["max_evaluated_candidates"] == expected_budget
    campaign_root = f"results/{effective['campaign_id']}"
    assert effective["runtime"]["hardware"]["artifacts_root"].replace("\\", "/") == (
        campaign_root + "/gem5"
    )
    assert effective["runtime"]["energy"]["artifacts_root"].replace("\\", "/") == (
        campaign_root + "/energy-work"
    )


@pytest.mark.parametrize(
    "method,campaign_id,expected_optimizer",
    [
        (
            "gemini",
            "confirmatory-gemini38-test",
            {"policy": "gemini_api", "model": "gemini-3.8-flash"},
        ),
        (
            "random",
            "confirmatory-random-test",
            {"policy": "random", "seed": 20260922},
        ),
    ],
)
def test_confirmatory_cli_uses_reviewed_model_seed_and_unique_id(
    method, campaign_id, expected_optimizer
):
    from scripts.run_experiment import main

    campaign = (
        ROOT
        / "experiment-contracts/campaigns/confirmatory-gemini38-vs-random-10.yaml"
    )
    with patch.object(
        sys,
        "argv",
        [
            "run_experiment.py",
            "--config",
            str(campaign),
            "--method",
            method,
            "--campaign-id",
            campaign_id,
        ],
    ), patch(
        "scripts.run_experiment.chia_entrypoint",
        return_value={"state": "completed", "experiments": []},
    ) as entrypoint:
        assert main() == 0

    effective = entrypoint.call_args.args[0]
    assert effective["campaign_id"] == campaign_id
    assert effective["iterations"] == 10
    assert effective["stopping"]["max_evaluated_candidates"] == 10
    assert all(
        effective["optimizer"][field] == expected
        for field, expected in expected_optimizer.items()
    )
    assert effective["runtime"]["hardware"]["artifacts_root"].replace(
        "\\", "/"
    ) == f"results/{campaign_id}/gem5"
    assert effective["runtime"]["energy"]["artifacts_root"].replace(
        "\\", "/"
    ) == f"results/{campaign_id}/energy-work"


def test_dataset_attestation_is_propagated_to_ray_workers(monkeypatch):
    from src.orchestration.chia import ray_worker_environment
    from src.orchestration.dispatch import ChiaDispatcher

    variable = "TEAM_ASSESSMENT_LLM_PERMISSION_CONFIRMED"
    monkeypatch.setenv(variable, "1")
    assert ray_worker_environment(
        {"software": {"dataset_permission_env": variable}}
    ) == {variable: "1"}

    fake_ray = SimpleNamespace(
        is_initialized=lambda: False,
        init=Mock(),
        cluster_resources=lambda: {
            "control": 1,
            "llama_cpp": 1,
            "gem5": 1,
        },
    )
    node_options = []
    fake_chia_module = ModuleType("chia.base.ChiaFunction")

    def fake_chia_function(**options):
        node_options.append(options)
        return lambda function: function

    fake_chia_module.ChiaFunction = fake_chia_function
    with patch.dict(
        sys.modules,
        {"ray": fake_ray, "chia.base.ChiaFunction": fake_chia_module},
    ):
        ChiaDispatcher("auto", env_vars={variable: "1"})

    fake_ray.init.assert_called_once_with(
        address="auto",
        runtime_env={"env_vars": {variable: "1"}},
    )
    assert node_options
    assert all(
        options["runtime_env"] == {"env_vars": {variable: "1"}}
        for options in node_options
    )


def test_release_preflight_checks_reviewed_head_identity(tmp_path, monkeypatch):
    from scripts.preflight_release import check_head

    model = tmp_path / "qwen2.5-0.5b-instruct-q5_k_m.gguf"
    model.write_bytes(b"reviewed-model")
    config = {
        "runtime": {
            "software": {
                "endpoint": "http://127.0.0.1:8081",
                "assets_root": str(tmp_path),
                "gguf": model.name,
                "model_sha256": "a" * 64,
                "context_tokens": 2048,
                "parallel_slots": 1,
                "dataset_permission_env": "TEAM_ASSESSMENT_LLM_PERMISSION_CONFIRMED",
                "questions_path": "data/questions/questions.json",
                "references_path": "data/references/answer_key.json",
                "dataset_id": "openstax-aligned-team-assessment-250-v1",
                "quality_method": "exact_option_text_accuracy",
            }
        }
    }
    monkeypatch.setenv("TEAM_ASSESSMENT_LLM_PERMISSION_CONFIRMED", "1")
    with patch(
        "scripts.preflight_release.runtime_preflight",
        return_value={
            "model_path": str(model),
            "model_sha256": "a" * 64,
            "context_tokens": 2048,
            "parallel_slots": 1,
            "runtime_build": "fixture",
        },
    ):
        result = check_head(config)

    assert result["role"] == "CHIA head node"
    assert result["model_path"] == str(model)
    assert result["context_tokens"] == 2048


def test_release_preflight_packages_checkout_for_repository_free_worker():
    from scripts.preflight_release import initialize_ray

    fake_ray = SimpleNamespace(is_initialized=lambda: False, init=Mock())
    with patch.dict(sys.modules, {"ray": fake_ray}):
        assert initialize_ray({"ray_address": "auto"}) is fake_ray

    fake_ray.init.assert_called_once_with(
        address="auto",
        runtime_env={"working_dir": str(ROOT)},
    )
