"""Software/hardware-owned runtime boundary tests; no production model or simulator required."""

import json
import shutil
import subprocess
import sys
from unittest.mock import patch
import pytest
from src.common.candidate import ROOT, baseline_candidate
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
from src.hardware.runner import parse_correctness, parse_gem5_version, verify_resolved
from src.tutor.runner import run_software_candidate
from src.tutor.llama_cpp_runtime import call_llama_cpp, extract_generation, preflight


def test_llama_cpp_maps_actual_request_fields():
    with patch("src.tutor.llama_cpp_runtime.request_json", return_value={}) as request:
        call_llama_cpp(
            endpoint="http://localhost:8081",
            model="test",
            system_prompt="system",
            user_prompt="question",
            temperature=0.2,
            max_output_tokens=64,
            timeout=5,
        )
    payload = request.call_args.args[2]
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 64
    assert payload["cache_prompt"] is False
    assert payload["messages"][1]["content"] == "question"
    assert request.call_args.kwargs["timeout"] == 5


def test_software_runner_repetitions_and_no_reference_leak():
    config = baseline_candidate()
    config["measurement"]["software_repetitions"] = 2
    reply = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": "Mass measures inertia and greater mass is harder to accelerate."
                },
            }
        ],
        "usage": {"prompt_tokens": 4, "completion_tokens": 12},
        "timings": {
            "prompt_ms": 10.0,
            "predicted_ms": 100.0,
            "predicted_per_second": 120.0,
            "cache_n": 0,
        },
        "system_fingerprint": "b10984-543158132",
    }
    evaluation = {
        "dataset_id": "fixture",
        "source_url": "https://openstax.org/fixture",
        "license": "CC BY 4.0",
        "items": [
            {
                "question": {"id": "q1", "question": "Question?"},
                "reference": {
                    "required_concepts": [["mass measures inertia"], ["harder to accelerate"]]
                },
            }
        ],
    }
    with (
        patch(
            "src.tutor.runner.map_final_tutor",
            return_value={
                "endpoint": "http://127.0.0.1:8081",
                "request": {
                    "model": "fixture",
                    "temperature": 0.0,
                    "max_output_tokens": 384,
                },
            },
        ),
        patch(
            "src.tutor.runner.preflight",
            return_value={"runtime_build": "fixture", "model_sha256": "a" * 64},
        ),
        patch("src.tutor.runner.load_evaluation_set", return_value=evaluation),
        patch("src.tutor.runner.call_llama_cpp", return_value=reply) as call,
    ):
        result = run_software_candidate(config, {"timeout_seconds": 30})
    assert len(result["samples"]) == 2
    assert result["metrics"]["answer_quality"] == 1.0
    assert all("reference" not in key for key in call.call_args.kwargs)
    assert "generated_answer" in result["samples"][0]


def test_llama_cpp_response_metrics_are_verified():
    answer, metrics = extract_generation(
        {
            "choices": [{"finish_reason": "stop", "message": {"content": "answer"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            "timings": {
                "prompt_ms": 25.0,
                "predicted_ms": 50.0,
                "predicted_per_second": 40.0,
            },
        }
    )
    assert answer == "answer"
    assert metrics["total_latency_ms"] == 75.0


def test_llama_cpp_preflight_pins_artifact_and_server_shape(tmp_path):
    model = tmp_path / "qwen.gguf"
    model.write_bytes(b"reviewed-model")
    import hashlib

    mapping = {
        "context_tokens": 2048,
        "parallel_slots": 1,
        "cpu_threads": 4,
        "artifact_assertions": {
            "model": "Qwen2.5 0.5B Instruct",
            "model_path": str(model),
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "weight_quantization": "Q5_K_M",
        },
    }
    with patch(
        "src.tutor.llama_cpp_runtime.request_json",
        side_effect=[
            {"status": "ok"},
            {
                "model_path": str(model),
                "total_slots": 1,
                "build_info": "b10984-543158132",
                "default_generation_settings": {"n_ctx": 2048},
            },
        ],
    ):
        identity = preflight("http://127.0.0.1:8081", mapping)

    assert identity["model_sha256"] == mapping["artifact_assertions"]["model_sha256"]
    assert identity["runtime_build"] == "b10984-543158132"


def test_hardware_cli_and_build_define_mapping():
    c = baseline_candidate()
    c["hardware"]["l1d_cache_kib"] = 32
    args = build_gem5_command(c)
    assert args[args.index("--l1d-cache-kib") + 1] == "32"
    assert args[args.index("--cores") + 1] == "2"
    assert "-DTHREADS=2" in build_attention_kernel_args(c)
    assert "-DREPETITIONS=10" in build_attention_kernel_args(c)

    qwen_shape = baseline_candidate()
    qwen_shape["workload"].update(
        {
            "query_heads": 14,
            "kv_heads": 2,
            "head_dimension": 64,
            "layers": 1,
        }
    )
    qwen_shape["measurement"]["kernel_iterations"] = 1
    qwen_args = build_attention_kernel_args(qwen_shape)
    assert "-DQUERY_HEADS=14" in qwen_args
    assert "-DKV_HEADS=2" in qwen_args
    assert "-DHEAD_DIM=64" in qwen_args
    assert "-DREPETITIONS=1" in qwen_args


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc is unavailable")
@pytest.mark.parametrize("query_heads,head_dimension", [(4, 32), (14, 64)])
def test_attention_proxy_compiles_and_runs_both_reviewed_shapes(
    tmp_path, query_heads, head_dimension
):
    executable = tmp_path / f"attention-{query_heads}-{head_dimension}"
    compile_result = subprocess.run(
        [
            shutil.which("gcc"),
            "-O2",
            "-std=c11",
            "-pthread",
            "-DCONTEXT=16",
            f"-DQUERY_HEADS={query_heads}",
            "-DKV_HEADS=2",
            f"-DHEAD_DIM={head_dimension}",
            "-DTHREADS=2",
            "-DREPETITIONS=1",
            str(ROOT / "gem5/attention_kv.c"),
            "-lm",
            "-o",
            str(executable),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    execution = subprocess.run(
        [str(executable)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert execution.returncode == 0, execution.stderr
    correctness = parse_correctness(
        execution.stdout,
        {"max_absolute_error": 0.0, "mean_squared_error": 0.0},
        enforce_tolerance=False,
    )
    assert correctness["query_heads"] == str(query_heads)
    assert correctness["head_dimension"] == str(head_dimension)
    assert correctness["kv_mapping"] == "grouped_query"


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc is unavailable")
@pytest.mark.parametrize(
    "source_name,query_heads,head_dimension",
    [
        ("attention_kv_original_proxy.c", 4, 32),
        ("attention_kv_qwen_proxy.c", 14, 64),
    ],
)
def test_frozen_proxy_entry_files_compile_and_report_locked_shapes(
    tmp_path, source_name, query_heads, head_dimension
):
    executable = tmp_path / source_name.removesuffix(".c")
    compile_result = subprocess.run(
        [
            shutil.which("gcc"),
            "-O2",
            "-std=c11",
            "-pthread",
            "-DCONTEXT=16",
            str(ROOT / "gem5" / source_name),
            "-lm",
            "-o",
            str(executable),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    execution = subprocess.run(
        [str(executable)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert execution.returncode == 0, execution.stderr
    correctness = parse_correctness(
        execution.stdout,
        {"max_absolute_error": 0.0, "mean_squared_error": 0.0},
        enforce_tolerance=False,
    )
    assert correctness["query_heads"] == str(query_heads)
    assert correctness["head_dimension"] == str(head_dimension)
    assert correctness["repetitions"] == "1"


def resolved(c):
    hw = c["hardware"]
    cpu_identity = {
        "RiscvO3CPU": {
            "type": "BaseO3CPU",
            "cxx_class": "gem5::o3::CPU",
        },
        "RiscvTimingSimpleCPU": {
            "type": "BaseTimingSimpleCPU",
            "cxx_class": "gem5::TimingSimpleCPU",
        },
    }[hw["cpu_model"]]

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
                    **cpu_identity,
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


def test_resolved_cpu_identity_requires_type_and_cxx_class():
    c = baseline_candidate()
    raw = resolved(c)
    raw["system"]["cpu"][0]["cxx_class"] = "gem5::TimingSimpleCPU"
    with pytest.raises(MetricsError):
        verify_resolved(raw, c)

    timing = baseline_candidate()
    timing["hardware"]["cpu_model"] = "RiscvTimingSimpleCPU"
    timing["hardware"]["issue_width"] = 1
    assert verify_resolved(resolved(timing), timing)


def test_gem5_version_comes_from_executed_simulation_banner():
    output = "gem5 Simulator System\ngem5 version 25.1.0.0\nstatus=PASS\n"
    assert parse_gem5_version(output) == "25.1.0.0"
    with pytest.raises(MetricsError):
        parse_gem5_version("simulation output without a version banner")


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
