from pathlib import Path

import pytest

from src.common.errors import ConfigError
from src.hardware.attention_kernel import (
    build_attention_kernel_args,
)


ROOT = Path(__file__).resolve().parents[1]


def qwen_config():
    return {
        "workload": {
            "context_tokens": 128,
            "query_heads": 14,
            "kv_heads": 2,
            "head_dimension": 64,
            "layers": 1,
        },
        "software": {
            "threads": 2,
        },
        "measurement": {
            "kernel_iterations": 1,
        },
    }


def test_qwen_attention_shape_is_supported():
    arguments = build_attention_kernel_args(
        qwen_config()
    )

    assert "-DCONTEXT=128" in arguments
    assert "-DQUERY_HEADS=14" in arguments
    assert "-DKV_HEADS=2" in arguments
    assert "-DHEAD_DIM=64" in arguments
    assert "-DTHREADS=2" in arguments
    assert "-DREPETITIONS=1" in arguments


def test_nondivisible_gqa_shape_is_rejected():
    config = qwen_config()
    config["workload"]["kv_heads"] = 3

    with pytest.raises(
        ConfigError,
        match="divisible",
    ):
        build_attention_kernel_args(config)


def test_odd_head_dimension_is_rejected():
    config = qwen_config()
    config["workload"]["head_dimension"] = 63

    with pytest.raises(
        ConfigError,
        match="even",
    ):
        build_attention_kernel_args(config)


def test_multiple_layers_are_rejected():
    config = qwen_config()
    config["workload"]["layers"] = 2

    with pytest.raises(
        ConfigError,
        match="one layer",
    ):
        build_attention_kernel_args(config)


def test_kernel_uses_grouped_query_mapping():
    source = (
        ROOT / "gem5" / "attention_kv.c"
    ).read_text(encoding="utf-8")

    assert "query_head % KV_HEADS" not in source
    assert "static int kv_head_for_query" in source
    assert "query_head / query_heads_per_kv" in source
    assert source.count("kv_head_for_query(query_head)") == 2
    assert (
        "#if QUERY_HEADS % KV_HEADS != 0"
        in source
    )
def test_kernel_distributes_all_heads():
    source = (
        ROOT / "gem5" / "attention_kv.c"
    ).read_text(encoding="utf-8")

    assert "query_head += THREADS" in source
    assert "int main_thread_id = 0;" in source
    assert "attention_worker(&main_thread_id);" in source
    assert "run_q4_head(0);" not in source
    assert "run_q4_head(2);" not in source
