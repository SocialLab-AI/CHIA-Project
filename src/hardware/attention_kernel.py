"""Hardware-owned kernel build mapper; used by both standalone and full-loop runners."""

from src.common.errors import ConfigError

SUPPORTED_ATTENTION_SHAPES = {
    (4, 2, 32, 1),
    (14, 2, 64, 1),
}


def build_attention_kernel_args(config):
    work = config["workload"]
    shape = (
        work["query_heads"],
        work["kv_heads"],
        work["head_dimension"],
        work["layers"],
    )
    if shape not in SUPPORTED_ATTENTION_SHAPES:
        raise ConfigError(
            "Attention shape is outside the reviewed original and Qwen-shaped profiles."
        )
    if work["query_heads"] % work["kv_heads"]:
        raise ConfigError(
            "Grouped-query attention requires query_heads divisible by kv_heads."
        )
    if work["head_dimension"] % 2:
        raise ConfigError("Packed Q4 requires an even head dimension.")
    return [
        f"-DCONTEXT={work['context_tokens']}",
        f"-DQUERY_HEADS={work['query_heads']}",
        f"-DKV_HEADS={work['kv_heads']}",
        f"-DHEAD_DIM={work['head_dimension']}",
        "-DTHREADS=2",
        f"-DREPETITIONS={config['measurement']['kernel_iterations']}",
    ]
