"""Hardware-owned kernel build mapper; used by both standalone and full-loop runners."""

from src.common.errors import ConfigError


def build_attention_kernel_args(config):
    work = config["workload"]
    if (work["query_heads"], work["kv_heads"], work["layers"]) != (4, 2, 1) or work[
        "head_dimension"
    ] % 2:
        raise ConfigError("Current attention kernel shape is unsupported.")
    return [
        f"-DCONTEXT={work['context_tokens']}",
        f"-DQUERY_HEADS={work['query_heads']}",
        f"-DKV_HEADS={work['kv_heads']}",
        f"-DHEAD_DIM={work['head_dimension']}",
        "-DTHREADS=2",
        f"-DREPETITIONS={config['measurement']['kernel_iterations']}",
    ]
