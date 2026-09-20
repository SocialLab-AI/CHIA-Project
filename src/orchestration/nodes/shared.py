"""Orchestration-owned retry envelope shared by SW/HW nodes; validation is never retried."""

import time
from src.common.logging import invoke


def execute_runtime(name, mapped, runtime, context, runner):
    events = []
    if mapped["event"]["status"] != "completed":
        return {
            "value": None,
            "event": {**mapped["event"], "node": name, "status": "skipped"},
            "events": [],
        }
    config = mapped["value"]["candidate"]
    retries = runtime.get("retries", 0)
    started = time.monotonic()
    for attempt in range(1, retries + 2):
        remaining = runtime["timeout_seconds"] - (time.monotonic() - started)
        if "deadline_epoch_seconds" in runtime:
            remaining = min(remaining, runtime["deadline_epoch_seconds"] - time.time())

        def operation():
            from src.common.errors import ExecutionTimeout

            if remaining <= 0:
                raise ExecutionTimeout("Node deadline expired before the next attempt.")
            bounded = {**runtime, "timeout_seconds": remaining}
            if "deadline_epoch_seconds" in runtime:
                bounded["deadline_epoch_seconds"] = runtime["deadline_epoch_seconds"]
            return runner(
                config,
                bounded,
                {
                    **context,
                    "attempt": attempt,
                    "run_id": context["run_id"] + "-a" + str(attempt),
                },
            )

        result = invoke(name, {**context, "attempt": attempt}, operation)
        events.append(result["event"])
        if (
            result["event"]["status"] == "completed"
            or not result["event"]["error"]["transient"]
            or attempt > retries
        ):
            result["events"] = events
            return result
        time.sleep(min(0.25 * attempt, max(0, remaining)))
