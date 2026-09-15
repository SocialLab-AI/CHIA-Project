"""CHIA hardware-only LLM optimization loop."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ray


def get(reference):
    """Ray Client-compatible result retrieval."""
    return ray.get(reference)

from src.hardware.knobs import load_design_space
from src.orchestration.nodes.hardware import run_gem5_candidate
from src.orchestration.nodes.optimizer import (
    propose_hardware_candidate,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = (
    PROJECT_ROOT / "results" / "hardware-optimization"
)


def _safe_campaign_id(value: str) -> str:
    """Validate a campaign identifier before using it as a directory."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ValueError(
            "campaign_id may contain only letters, numbers, "
            "periods, underscores, and hyphens"
        )

    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    """Write JSON atomically so interrupted writes do not corrupt results."""
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_summary(
    campaign_directory: Path,
    campaign_id: str,
    state: str,
    requested_iterations: int,
    history: list[dict[str, Any]],
) -> None:
    """Save the complete optimization history after every iteration."""
    _write_json(
        campaign_directory / "summary.json",
        {
            "campaign_id": campaign_id,
            "mode": "hardware_only",
            "state": state,
            "requested_iterations": requested_iterations,
            "completed_iterations": len(
                [
                    record
                    for record in history
                    if record.get("status") == "completed"
                ]
            ),
            "updated_at": _utc_timestamp(),
            "experiments": history,
        },
    )


def chia_entrypoint(
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run Gemini-guided hardware optimization and persist every result.

    Gemini proposes hardware knobs locally. CHIA schedules gem5 on
    the worker advertising the custom `gem5` resource.
    """

    config = config or {}

    design_space = config.get("design_space") or load_design_space()
    iterations = int(config.get("iterations", 1))
    optimizer_model = config.get("optimizer_model")
    history = list(config.get("history", []))

    if iterations < 1:
        raise ValueError("iterations must be at least 1")

    default_campaign_id = datetime.now(timezone.utc).strftime(
        "hardware-%Y%m%dT%H%M%SZ"
    )
    campaign_id = _safe_campaign_id(
        str(config.get("campaign_id", default_campaign_id))
    )

    results_root = Path(
        config.get("results_root", DEFAULT_RESULTS_ROOT)
    ).expanduser().resolve()

    campaign_directory = results_root / campaign_id
    campaign_directory.mkdir(parents=True, exist_ok=True)

    experiments = []

    _save_summary(
        campaign_directory=campaign_directory,
        campaign_id=campaign_id,
        state="running",
        requested_iterations=iterations,
        history=history,
    )

    for iteration in range(iterations):
        candidate = None

        try:
            candidate = propose_hardware_candidate(
                design_space=design_space,
                history=history,
                model=optimizer_model,
            )

            result_reference = (
                run_gem5_candidate.chia_remote(candidate)
            )
            hardware_result = get(result_reference)

            record = {
                "iteration": iteration + 1,
                "timestamp": _utc_timestamp(),
                "status": "completed",
                "candidate": candidate,
                "hardware_result": hardware_result,
            }

        except Exception as error:
            record = {
                "iteration": iteration + 1,
                "timestamp": _utc_timestamp(),
                "status": "failed",
                "candidate": candidate,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }

            history.append(record)
            experiments.append(record)

            _write_json(
                campaign_directory
                / f"iteration-{iteration + 1:03d}.json",
                record,
            )
            _save_summary(
                campaign_directory=campaign_directory,
                campaign_id=campaign_id,
                state="failed",
                requested_iterations=iterations,
                history=history,
            )

            raise

        history.append(record)
        experiments.append(record)

        _write_json(
            campaign_directory
            / f"iteration-{iteration + 1:03d}.json",
            record,
        )
        _save_summary(
            campaign_directory=campaign_directory,
            campaign_id=campaign_id,
            state="running",
            requested_iterations=iterations,
            history=history,
        )

    _save_summary(
        campaign_directory=campaign_directory,
        campaign_id=campaign_id,
        state="completed",
        requested_iterations=iterations,
        history=history,
    )

    return {
        "status": "completed",
        "mode": "hardware_only",
        "campaign_id": campaign_id,
        "iterations": iterations,
        "experiments": experiments,
        "history": history,
        "results_directory": str(campaign_directory),
    }
