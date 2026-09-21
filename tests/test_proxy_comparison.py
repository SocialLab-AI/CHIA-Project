"""Pure checks for the repeated original-versus-Qwen proxy comparison."""

import json
import sys

import pytest
import yaml

import scripts.run_proxy_comparison as comparison
from scripts.run_proxy_comparison import aggregate_trials
from src.common.errors import MetricsError


def _sample(seconds, max_error, mse, normalized_rmse, normalized_max):
    return {
        "metrics": {
            "simulated_seconds": seconds,
            "instructions": 1000,
            "aggregate_ipc": 1.5,
            "l2_miss_rate": 0.5,
        },
        "correctness": {
            "max_absolute_error": max_error,
            "mean_squared_error": mse,
            "root_mean_squared_error": mse**0.5,
            "reference_rms": 0.25,
            "reference_max_absolute": 0.5,
            "normalized_rmse": normalized_rmse,
            "normalized_max_error": normalized_max,
        },
    }


def test_trial_aggregation_keeps_samples_and_worst_correctness():
    result = aggregate_trials(
        [
            _sample(1.0, 0.009, 0.000009, 0.02, 0.03),
            _sample(1.2, 0.011, 0.000012, 0.04, 0.05),
            _sample(1.1, 0.010, 0.000010, 0.03, 0.04),
        ],
        {"max_absolute_error": 0.01, "mean_squared_error": 0.00001},
    )

    assert result["trial_count"] == 3
    assert result["metrics"]["simulated_seconds"] == pytest.approx(1.1)
    assert result["metrics"]["simulated_seconds_median"] == pytest.approx(1.1)
    assert result["correctness"]["max_absolute_error"] == pytest.approx(0.011)
    assert result["correctness"]["normalized_rmse"] == pytest.approx(0.04)
    assert result["correctness_within_reviewed_tolerance"] is False


def test_trial_aggregation_rejects_single_sample():
    with pytest.raises(MetricsError, match="At least two"):
        aggregate_trials(
            [_sample(1.0, 0.001, 0.000001, 0.01, 0.01)],
            {"max_absolute_error": 0.01, "mean_squared_error": 0.00001},
        )


def test_comparison_configuration_is_strict_and_portable(tmp_path, monkeypatch):
    monkeypatch.setattr(comparison, "ROOT", tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for name in ("model-profile.json", "native-context-sweep.json"):
        (evidence / name).write_text(json.dumps({}), encoding="utf-8")
    config = {
        "experiment_id": "proxy-comparison-test",
        "contexts": [128, 256, 512, 1024, 2048],
        "trials_per_context": 3,
        "results_root": "results/proxy-comparison",
        "native_evidence_directory": "evidence",
        "hardware": {
            "mode": "chia",
            "ray_address": "auto",
            "image": "ghcr.io/gem5/devcontainer:v25-1",
            "timeout_seconds": 1800,
            "correctness_tolerance": {
                "max_absolute_error": 0.01,
                "mean_squared_error": 0.00001,
            },
        },
    }
    path = tmp_path / "comparison.local.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")

    loaded = comparison.load_config(path)
    assert loaded["trials_per_context"] == 3
    assert loaded["hardware"]["mode"] == "chia"

    config["trials_per_context"] = 1
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="between two and five"):
        comparison.load_config(path)


def test_validate_only_reports_plan_without_executing(monkeypatch, capsys):
    config = {
        "experiment_id": "proxy-comparison-test",
        "contexts": [128, 256, 512, 1024, 2048],
        "trials_per_context": 3,
    }
    native = {
        "model_sha256": "abc",
        "contexts": [
            {
                "context_tokens": context,
                "benchmark_provenance": {"type_k": "f16", "type_v": "f16"},
            }
            for context in config["contexts"]
        ],
    }
    monkeypatch.setattr(comparison, "load_config", lambda _path: config)
    monkeypatch.setattr(
        comparison,
        "load_native_evidence",
        lambda _config: ({"model_sha256": "abc"}, native),
    )
    monkeypatch.setattr(
        comparison,
        "run_comparison",
        lambda _config: pytest.fail("validate-only must not execute hardware work"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_proxy_comparison.py", "--config", "unused.yaml", "--validate-only"],
    )

    assert comparison.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["planned_hardware_jobs"] == 30
    assert output["native_kv_cache_types"] == {"key": "f16", "value": "f16"}
    assert output["execution"] == "not_started"
