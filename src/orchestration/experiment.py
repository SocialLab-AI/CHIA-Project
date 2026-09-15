"""Single candidate graph executor; orchestration owns both local and CHIA paths."""

import time
import uuid
from src.common.candidate import Candidate
from src.common.security import safe_id, no_secrets, canonical
from src.common.errors import failure
from src.common.logging import utc_now
from src.common.records import provenance, persist_record
from src.orchestration.dispatch import LocalDispatcher


def run_experiment(
    config,
    *,
    runtime=None,
    dispatcher=None,
    results_root=None,
    campaign_id="local",
    iteration=1,
    policy="deterministic",
    optimizer_metadata=None,
):
    from src.common.candidate import ROOT

    runtime = runtime or {
        "software": {"timeout_seconds": 120, "retries": 0},
        "hardware": {"timeout_seconds": 600, "retries": 0},
    }
    dispatcher = dispatcher or LocalDispatcher()
    results_root = results_root or ROOT / "results/full-loop"
    safe_id(campaign_id)
    run_id = "run-" + uuid.uuid4().hex
    started = utc_now()
    record = {
        "schema_version": "0.3.0",
        "campaign_id": campaign_id,
        "iteration": iteration,
        "run_id": run_id,
        "candidate_id": "0" * 64,
        "candidate": None,
        "started_at": started,
        "ended_at": started,
        "status": "failed",
        "software_result": None,
        "hardware_result": None,
        "evaluation": None,
        "failure": None,
        "events": [],
        "provenance": provenance(),
        "optimizer": {"policy": policy, "metadata": optimizer_metadata or {}},
    }
    refs = []
    stage = "validation"
    try:
        # Invalid/secret-bearing objects are not serialized into failure records.
        snapshot = Candidate.from_dict(config)
        record["candidate"], record["candidate_id"] = (
            snapshot.config,
            snapshot.candidate_id,
        )
        context = {
            "campaign_id": campaign_id,
            "iteration": iteration,
            "run_id": run_id,
            "candidate_id": snapshot.candidate_id,
        }
        deadline = time.monotonic() + runtime.get(
            "graph_timeout_seconds",
            max(
                runtime["software"]["timeout_seconds"],
                runtime["hardware"]["timeout_seconds"],
            )
            + 60,
        )
        validated = dispatcher.submit("validation", snapshot.config, context)
        refs.append(validated)
        mapped = dispatcher.submit("mapping", validated, context)
        refs.append(mapped)
        stage = "execution"
        sw = dispatcher.submit("software", mapped, runtime["software"], context)
        refs.append(sw)
        hw = dispatcher.submit("hardware", mapped, runtime["hardware"], context)
        refs.append(hw)
        evaluation = dispatcher.submit("evaluation", mapped, sw, hw, context)
        refs.append(evaluation)
        for name, reference in (
            ("validation", validated),
            ("mapping", mapped),
            ("software", sw),
            ("hardware", hw),
            ("evaluation", evaluation),
        ):
            result = dispatcher.get(
                reference, timeout=max(0.001, deadline - time.monotonic())
            )
            record["events"].extend(result.get("events", [result["event"]]))
            if name in {"software", "hardware"}:
                # Malformed runtime output must not prevent a durable failed record.
                canonical(result["value"])
                no_secrets(result["value"])
                record[name + "_result"] = result["value"]
            if name == "evaluation":
                record["evaluation"] = result["value"]
            if result["event"]["status"] == "failed" and record["failure"] is None:
                record["failure"] = result["event"]["error"]
        if record["failure"] is None:
            record["status"] = "completed"
        stage = "record"
    except Exception as error:
        record["failure"] = failure(error, stage)
        record["status"] = "rejected" if stage == "validation" else "failed"
        for reference in refs:
            try:
                dispatcher.cancel(reference)
            except Exception:
                pass
    record["ended_at"] = utc_now()
    if record["status"] == "completed":
        try:
            reference = dispatcher.submit("record", record, str(results_root))
            return dispatcher.get(reference, timeout=30)
        except Exception as error:
            record["status"] = "failed"
            record["failure"] = failure(error, "record")
    # Driver fallback preserves rejected candidates and worker/persistence failures.
    return persist_record(record, results_root)
