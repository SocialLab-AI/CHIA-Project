"""Run-scoped structured events; integration owns the shared log contract."""

import logging
import json
import socket
import time
from datetime import datetime, timezone
from src.common.errors import failure


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_logger(name):
    return logging.getLogger(name)


def invoke(node, context, operation):
    """Return a success/failure envelope; no model prompts or raw stdout are logged."""
    started, clock = utc_now(), time.monotonic()
    event = {
        **context,
        "node": node,
        "worker": socket.gethostname(),
        "started_at": started,
    }
    print(json.dumps({**event, "status": "started", "error": None}), flush=True)
    try:
        value = operation()
        event.update(status="completed", error=None)
    except Exception as error:
        value = None
        event.update(status="failed", error=failure(error, node))
    event.update(ended_at=utc_now(), duration_ms=(time.monotonic() - clock) * 1000)
    print(json.dumps(event, allow_nan=False), flush=True)
    return {"value": value, "event": event}
