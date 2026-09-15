"""Adam software node; orchestration owns dispatch, tutor owns Ollama execution."""

from src.tutor.runner import run_software_candidate
from src.orchestration.nodes.shared import execute_runtime


def software_node(mapped, runtime, context):
    return execute_runtime("software", mapped, runtime, context, run_software_candidate)
