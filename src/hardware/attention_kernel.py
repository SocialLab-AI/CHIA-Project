"""Hardware-owned attention-kernel build mapper."""

from src.common.errors import ConfigError


PROXY_THREADS = 2


def build_attention_kernel_args(config):
    """Convert a validated workload into compiler definitions."""

    workload = config["workload"]
    measurement = config["measurement"]

    context_tokens = workload["context_tokens"]
    query_heads = workload["query_heads"]
    kv_heads = workload["kv_heads"]
    head_dimension = workload["head_dimension"]
    layers = workload["layers"]
    repetitions = measurement["kernel_iterations"]

    if layers != 1:
        raise ConfigError(
            "The current attention proxy supports exactly one layer."
        )

    if query_heads < kv_heads:
        raise ConfigError(
            "Query heads must be greater than or equal to KV heads."
        )

    if query_heads % kv_heads != 0:
        raise ConfigError(
            "Query heads must be divisible by KV heads."
        )

    if head_dimension % 2 != 0:
        raise ConfigError(
            "Head dimension must be even for packed Q4 storage."
        )

    return [
        f"-DCONTEXT={context_tokens}",
        f"-DQUERY_HEADS={query_heads}",
        f"-DKV_HEADS={kv_heads}",
        f"-DHEAD_DIM={head_dimension}",
        f"-DTHREADS={PROXY_THREADS}",
        f"-DREPETITIONS={repetitions}",
    ]
