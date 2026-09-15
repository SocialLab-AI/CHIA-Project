"""YSF execution node; orchestration owns dispatch and hardware owns the runner."""

from src.hardware.runner import run_gem5_candidate
from src.orchestration.nodes.shared import execute_runtime


def hardware_node(mapped, runtime, context):
    return execute_runtime("hardware", mapped, runtime, context, run_gem5_candidate)
