"""Software/hardware-owned runtime boundary tests; no production model or simulator required."""

import json
import sys
from unittest.mock import patch
import pytest
from src.common.candidate import baseline_candidate
from src.common.errors import (
    MetricsError,
    PreflightError,
    ExecutionTimeout,
    RuntimeExecutionError,
    failure,
)
from src.common.process import run_process
from src.hardware.attention_kernel import build_attention_kernel_args
from src.hardware.gem5 import build_gem5_command
from src.hardware.runner import verify_resolved
from src.tutor.runner import run_software_candidate
from src.tutor.ollama_runtime import call_ollama


def test_ollama_maps_actual_request_fields():
    with patch("src.tutor.ollama_runtime.request_json", return_value={}) as request:
        call_ollama(
            endpoint="http://localhost:11434",
            model="test",
            system_prompt="system",
            user_prompt="question",
            temperature=0.2,
            max_output_tokens=64,
            cpu_threads=4,
            timeout=5,
        )
    assert request.call_args.args[2]["options"] == {
        "temperature": 0.2,
        "num_predict": 64,
        "num_thread": 4,
    }
    assert "batch_size" not in request.call_args.args[2]["options"]
    assert request.call_args.kwargs["timeout"] == 5


def test_software_runner_repetitions_and_no_reference_leak():
    config = baseline_candidate()
    config["measurement"]["software_repetitions"] = 2
    reply = {
        "done": True,
        "response": "cache answer",
        "total_duration": 1000000,
        "load_duration": 0,
        "prompt_eval_duration": 1000,
        "eval_duration": 100000,
        "prompt_eval_count": 4,
        "eval_count": 2,
    }
    with (
        patch(
            "src.tutor.runner.preflight",
            return_value={"runtime_version": "fixture", "model_digest": "fixture"},
        ),
        patch("src.tutor.runner.call_ollama", return_value=reply) as call,
    ):
        result = run_software_candidate(config)
    assert len(result["samples"]) == 2
    assert result["metrics"]["answer_quality"] is None
    assert all("reference" not in k for k in call.call_args.kwargs)
    assert "response" not in result["samples"][0]


def test_hardware_cli_and_build_define_mapping():
    c = baseline_candidate()
    c["hardware"]["l1d_cache_kib"] = 32
    args = build_gem5_command(c)
    assert args[args.index("--l1d-cache-kib") + 1] == "32"
    assert args[args.index("--cores") + 1] == "2"
    assert "-DTHREADS=2" in build_attention_kernel_args(c)
    assert "-DREPETITIONS=10" in build_attention_kernel_args(c)


def resolved(c):
    hw = c["hardware"]

    def cache(prefix):
        return {
            "size": hw[prefix + "_cache_kib"] * 1024,
            "assoc": hw[prefix + "_associativity"],
            **{
                k: hw[prefix + "_latency_cycles"]
                for k in ("tag_latency", "data_latency", "response_latency")
            },
        }

    return {
        "system": {
            "cpu": [
                {
                    "type": hw["cpu_model"],
                    "issueWidth": hw["issue_width"],
                    "icache": cache("l1i"),
                    "dcache": cache("l1d"),
                }
                for _ in range(2)
            ],
            "l2cache": cache("l2"),
            "cpu_clk_domain": {"clock": [round(1000 / hw["frequency_ghz"])]},
            "clk_domain": {"clock": [1000]},
        }
    }


def test_resolved_config_verification_detects_silent_mapping_failure():
    c = baseline_candidate()
    raw = resolved(c)
    assert verify_resolved(raw, c)
    raw["system"]["cpu"][1]["dcache"]["size"] = 1024
    with pytest.raises(MetricsError):
        verify_resolved(raw, c)


def test_no_unapproved_numerical_tolerance():
    from src.hardware.runner import run_gem5_candidate

    with patch("src.hardware.runner.run_process") as launch:
        with pytest.raises(PreflightError):
            run_gem5_candidate(baseline_candidate())
    launch.assert_not_called()


def test_subprocess_timeout_is_enforced(tmp_path):
    with pytest.raises(ExecutionTimeout):
        run_process(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            timeout=0.1,
        )


def test_process_output_summaries_do_not_expose_values(tmp_path):
    result = run_process(
        [sys.executable, "-c", 'print("private-output")'], cwd=tmp_path, timeout=5
    )
    assert result["stdout_summary"]["content"] == "[omitted]"
    assert "private-output" not in json.dumps(result["stdout_summary"])


def test_runtime_failure_preserves_only_safe_diagnostic_metadata():
    error = RuntimeExecutionError("Subprocess failed with exit code 2.")
    error.runtime_stage = "compile_kernel"
    error.stdout_summary = {
        "bytes": 14,
        "sha256": "a" * 64,
        "content": "[omitted]",
    }
    error.stderr_summary = {
        "bytes": 21,
        "sha256": "b" * 64,
        "content": "[omitted]",
    }

    recorded = failure(error, "hardware")

    assert recorded["runtime_stage"] == "compile_kernel"
    assert recorded["stderr_summary"]["bytes"] == 21
    assert "private-output" not in json.dumps(recorded)
