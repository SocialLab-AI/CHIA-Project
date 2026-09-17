"""Persistence node; receives verified outcomes and never model-authored metrics."""

import socket
import time
from src.common.logging import utc_now
from src.common.records import persist_record, validate_record


def record_node(record, results_root):
    start = time.monotonic()
    started = utc_now()
    validate_record(record)
    record["events"].append(
        {
            "campaign_id": record["campaign_id"],
            "run_id": record["run_id"],
            "candidate_id": record["candidate_id"],
            "iteration": record["iteration"],
            "node": "record",
            "worker": socket.gethostname(),
            "started_at": started,
            "ended_at": utc_now(),
            "duration_ms": (time.monotonic() - start) * 1000,
            "status": "completed",
            "error": None,
        }
    )
    return persist_record(record, results_root)
