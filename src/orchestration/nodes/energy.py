"""Energy node joins the exact gem5 run to its isolated estimate."""

from src.hardware.energy_estimator import run_energy_candidate
from src.orchestration.nodes.shared import execute_runtime


def energy_node(mapped, hardware, runtime, context):
    if hardware["event"]["status"] != "completed":
        return {
            "value": None,
            "event": {**hardware["event"], "node": "energy", "status": "skipped"},
            "events": [],
        }

    def runner(config, bounded_runtime, bounded_context):
        return run_energy_candidate(config, hardware["value"], bounded_runtime, bounded_context)

    return execute_runtime("energy", mapped, runtime, context, runner)
