"""Verify Issue #60 model evidence, benchmark parsers and analysis logic."""

import json
from pathlib import Path

import pytest
import yaml

from src.common.errors import MetricsError
from src.hardware.proxy_fidelity import (
    CONTEXT_LENGTHS,
    analyze_fidelity,
    architecture_comparison,
    render_report,
    render_trend_svg,
    spearman_rank_correlation,
)
from src.tutor.benchmark import (
    parse_gnu_time,
    parse_llama_bench_json,
    parse_perf_stat,
)
from src.tutor.model_profile import extract_gguf_profile
from scripts.run_proxy_fidelity import load_config


def test_extract_exact_qwen_metadata_from_gguf_header(tmp_path):
    """The model profile must come from the artifact, not a filename guess."""

    gguf = pytest.importorskip("gguf")
    path = tmp_path / "qwen-test-q5.gguf"
    writer = gguf.GGUFWriter(path, "qwen2")
    writer.add_name("Qwen2.5 0.5B Instruct test header")
    writer.add_block_count(24)
    writer.add_context_length(32768)
    writer.add_embedding_length(896)
    writer.add_feed_forward_length(4864)
    writer.add_head_count(14)
    writer.add_head_count_kv(2)
    writer.add_rope_dimension_count(64)
    writer.add_file_type(gguf.LlamaFileType.MOSTLY_Q5_K_M)
    writer.add_quantization_version(2)
    writer.add_chat_template("{{ messages }}")
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()

    profile = extract_gguf_profile(path)

    assert profile["architecture"] == "qwen2"
    assert profile["layers"] == 24
    assert profile["hidden_size"] == 896
    assert profile["query_heads"] == 14
    assert profile["kv_heads"] == 2
    assert profile["head_dimension"] == 64
    assert profile["feed_forward_dimension"] == 4864
    assert profile["maximum_context_length"] == 32768
    assert profile["quantization"] == "Q5_K_M"
    assert profile["chat_template_present"] is True
    json.dumps(profile)

    # The extractor must release GGUFReader's memory map before returning.
    path.unlink()


def test_architecture_comparison_preserves_current_proxy_mismatch():
    model = {
        "layers": 24,
        "hidden_size": 896,
        "query_heads": 14,
        "kv_heads": 2,
        "head_dimension": 64,
        "feed_forward_dimension": 4864,
        "maximum_context_length": 32768,
        "quantization": "Q5_K_M",
        "kv_cache_quantization": "F16",
    }
    proxy = {
        "layers": 1,
        "hidden_size": None,
        "query_heads": 4,
        "kv_heads": 2,
        "head_dimension": 32,
        "feed_forward_dimension": None,
        "maximum_tested_context": 2048,
        "weight_quantization": None,
        "kv_quantization": "Q4",
    }

    rows = architecture_comparison(model, proxy)
    by_parameter = {row["parameter"]: row for row in rows}

    assert by_parameter["Transformer layers"]["match"] == "no"
    assert by_parameter["Query heads"]["match"] == "no"
    assert by_parameter["KV heads"]["match"] == "yes"
    assert by_parameter["Head dimension"]["match"] == "no"
    assert by_parameter["Hidden size"]["match"] == "not_modeled"
    assert by_parameter["KV-cache quantization"]["match"] == "unknown"


def test_spearman_handles_order_ties_and_constant_rejection():
    assert spearman_rank_correlation([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert spearman_rank_correlation([1, 2, 3], [30, 20, 10]) == pytest.approx(-1.0)
    assert spearman_rank_correlation([1, 1, 2], [4, 4, 8]) == pytest.approx(1.0)
    with pytest.raises(MetricsError, match="constant vector"):
        spearman_rank_correlation([1, 1, 1], [1, 2, 3])


def test_native_measurement_parsers_keep_units_and_scope():
    benchmark = {
        "build_commit": "abc123",
        "build_number": 1,
        "cpu_info": "test CPU",
        "gpu_info": "",
        "backends": "CPU",
        "model_filename": "model.gguf",
        "model_type": "0.5B",
        "model_size": 522186592,
        "model_n_params": 494000000,
        "n_batch": 2048,
        "n_ubatch": 512,
        "n_threads": 4,
        "n_prompt": 128,
        "n_gen": 0,
        "n_gpu_layers": 0,
        "flash_attn": False,
        "type_k": "f16",
        "type_v": "f16",
        "avg_ns": 2_000_000,
        "stddev_ns": 100_000,
        "avg_ts": 64.0,
        "stddev_ts": 1.0,
        "samples_ns": [1_900_000, 2_100_000],
        "samples_ts": [67.36, 60.95],
    }
    parsed = parse_llama_bench_json(json.dumps([benchmark]), 128, 2)
    resources = parse_gnu_time(
        "Maximum resident set size (kbytes): 2048\n"
        "Percent of CPU this job got: 390%\n"
    )
    counters = parse_perf_stat(
        "1000,,cycles,1,100.00,,\n"
        "500,,instructions,1,100.00,,\n"
        "<not supported>,,cache-misses,1,0.00,,\n"
    )

    assert parsed["average_latency_ms"] == 2.0
    assert parsed["prompt_tokens_per_second"] == 64.0
    assert resources["peak_rss_bytes"] == 2 * 1024 * 1024
    assert resources["process_cpu_utilization_percent"] == 390.0
    assert counters == {"cycles": 1000.0, "instructions": 500.0}


def test_analysis_labels_partial_proxy_and_renders_artifacts():
    model = {
        "architecture": "qwen2",
        "model_sha256": "a" * 64,
        "quantization": "Q5_K_M",
        "layers": 24,
        "hidden_size": 896,
        "query_heads": 14,
        "kv_heads": 2,
        "head_dimension": 64,
        "feed_forward_dimension": 4864,
        "maximum_context_length": 32768,
        "kv_cache_quantization": "runtime-dependent",
    }
    native = {
        "contexts": [
            {"context_tokens": context, "average_latency_ms": value}
            for context, value in zip(CONTEXT_LENGTHS, (1, 2, 4, 8, 16))
        ]
    }
    hardware = {
        "contexts": [
            {
                "context_tokens": context,
                "metrics": {"simulated_seconds": value},
            }
            for context, value in zip(CONTEXT_LENGTHS, (2, 3, 5, 9, 17))
        ],
        "sensitivity": [
            {"case_id": "slow", "metrics": {"simulated_seconds": 2.0}},
            {"case_id": "fast", "metrics": {"simulated_seconds": 1.0}},
        ],
    }

    analysis = analyze_fidelity(model, native, hardware)
    report = render_report(analysis, model)
    svg = render_trend_svg(analysis)

    assert analysis["context_spearman_rho"] == pytest.approx(1.0)
    assert analysis["proxy_hardware_ranking"] == ["fast", "slow"]
    assert analysis["native_hardware_ranking"] is None
    assert analysis["configuration_rank_correlation"] is None
    assert analysis["conclusion"] == "B_PARTIAL_PROXY"
    assert "complete Qwen inference" in report
    assert "unavailable on the current cluster" in report
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')


def test_analysis_rejects_incomplete_context_evidence():
    with pytest.raises(MetricsError, match="must cover"):
        analyze_fidelity(
            {},
            {"contexts": [{"context_tokens": 128, "average_latency_ms": 1.0}]},
            {
                "contexts": [
                    {
                        "context_tokens": 128,
                        "metrics": {"simulated_seconds": 1.0},
                    }
                ]
            },
        )


def test_issue_configuration_is_strict_and_candidate_validated(tmp_path):
    source = Path(__file__).resolve().parents[1] / (
        "experiment-contracts/testing/proxy-fidelity.server.example.yaml"
    )
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["results_root"] = "results/proxy-fidelity-test"
    valid = tmp_path / "valid.yaml"
    valid.write_text(yaml.safe_dump(config), encoding="utf-8")

    loaded = load_config(valid)
    assert tuple(loaded["contexts"]) == CONTEXT_LENGTHS
    assert len(loaded["hardware"]["sensitivity"]) == 2

    config["native"]["model_sha256"] = "not-a-digest"
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        load_config(invalid)
