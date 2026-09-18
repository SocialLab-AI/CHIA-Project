#!/usr/bin/env python3
"""Issue #33 Gemini-guided software-only optimization.

Gemini proposes only:
    - temperature
    - max_output_tokens

Deterministic code owns:
    - validation
    - model/runtime execution
    - quality evaluation
    - metrics
    - duplicate rejection
    - persistence

No gem5 or hardware worker is used by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from src.common.candidate import (
    Candidate,
    ROOT,
    baseline_candidate,
)
from src.common.security import (
    finite_number,
    no_secrets,
    strict_json,
    within,
)
from src.orchestration.gemini_api import (
    GeminiSoftwareOptimizer,
)
from src.tutor.runner import (
    run_software_candidate,
    software_failure,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def load_software_runtime(path: Path) -> dict:
    config = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    runtime = config.get(
        "runtime",
        {},
    ).get("software")

    if not isinstance(runtime, dict):
        raise ValueError(
            "Config must contain runtime.software."
        )

    return runtime


def load_pricing(model: str) -> dict:
    path = (
        ROOT
        / "experiment-contracts"
        / "policies"
        / "compute-policy.yaml"
    )

    policy = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    try:
        return policy["gemini"]["models"][model]
    except KeyError as exc:
        raise ValueError(
            f"No pricing configured for Gemini model {model}."
        ) from exc


def load_history_summary(path: Path, repetitions: int) -> dict:
    """Load validated prior SW results for cross-campaign deduplication."""

    resolved = within(
        ROOT,
        path,
        exists=True,
    )
    raw = resolved.read_text(encoding="utf-8")
    summary = strict_json(raw)
    no_secrets(summary)

    if (
        not isinstance(summary, dict)
        or summary.get("scope") != "software_only"
        or not isinstance(summary.get("records"), list)
    ):
        raise ValueError(
            "History summary must be a software-only campaign summary."
        )

    if summary.get("repetitions_per_question") != repetitions:
        raise ValueError(
            "History and new campaign must use the same repetitions."
        )

    history = []
    seen = set()

    for index, record in enumerate(summary["records"], start=1):
        if not isinstance(record, dict):
            raise ValueError(
                f"History record {index} must be an object."
            )

        status = record.get("status")
        software = record.get("software")
        candidate_id = record.get("candidate_id")
        metrics = record.get("metrics")

        if status not in {"completed", "failed"}:
            raise ValueError(
                f"History record {index} has an invalid status."
            )

        candidate = baseline_candidate()
        candidate["software"] = software
        candidate["measurement"]["software_repetitions"] = repetitions
        snapshot = Candidate.from_dict(candidate)

        if candidate_id != snapshot.candidate_id:
            raise ValueError(
                f"History record {index} candidate ID is invalid."
            )

        if candidate_id in seen:
            raise ValueError(
                "History summary contains duplicate candidate IDs."
            )

        if status == "completed":
            if not isinstance(metrics, dict):
                raise ValueError(
                    f"History record {index} is missing metrics."
                )

            finite_number(
                metrics.get("answer_quality"),
                "history answer_quality",
            )
            finite_number(
                metrics.get("latency_ms"),
                "history latency_ms",
                positive=True,
            )
        elif metrics is not None:
            raise ValueError(
                f"Failed history record {index} must not have metrics."
            )

        normalized = baseline_candidate()
        normalized["software"] = dict(software)
        normalized["software"]["temperature"] = float(
            normalized["software"]["temperature"]
        )
        normalized["measurement"]["software_repetitions"] = repetitions

        # Older summaries may distinguish JSON 0 from 0.0 in the digest.
        # Block both IDs so the same scientific configuration is not rerun.
        seen.add(candidate_id)
        seen.add(Candidate.from_dict(normalized).candidate_id)
        history.append(
            {
                "candidate_id": candidate_id,
                "status": status,
                "software": software,
                "metrics": metrics,
                "source": "history_summary",
            }
        )

    return {
        "path": str(resolved.relative_to(ROOT)),
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "history": history,
        "seen": seen,
    }


def comparison_summary(records: list[dict]) -> dict:
    """Summarize completed candidates across imported and new results."""

    completed = [
        record
        for record in records
        if record["status"] == "completed"
    ]

    def best(metric, *, maximize=False):
        eligible = [
            record
            for record in completed
            if isinstance(record.get("metrics"), dict)
            and isinstance(record["metrics"].get(metric), (int, float))
            and not isinstance(record["metrics"].get(metric), bool)
        ]
        if not eligible:
            return None
        chosen = (max if maximize else min)(
            eligible,
            key=lambda record: record["metrics"][metric],
        )
        return {
            "candidate_id": chosen["candidate_id"],
            "value": chosen["metrics"][metric],
        }

    pareto = []
    for target in completed:
        target_quality = target["metrics"]["answer_quality"]
        target_latency = target["metrics"]["latency_ms"]
        dominated = any(
            other is not target
            and other["metrics"]["answer_quality"] >= target_quality
            and other["metrics"]["latency_ms"] <= target_latency
            and (
                other["metrics"]["answer_quality"] > target_quality
                or other["metrics"]["latency_ms"] < target_latency
            )
            for other in completed
        )
        if not dominated:
            pareto.append(target["candidate_id"])

    return {
        "completed_candidate_count": len(completed),
        "pareto_candidate_ids": pareto,
        "best_by": {
            "answer_quality": best("answer_quality", maximize=True),
            "median_latency_ms": best("latency_ms"),
            "mean_latency_ms": best("mean_latency_ms"),
            "p95_latency_ms": best("p95_latency_ms"),
            "throughput_qps": best("throughput_qps", maximize=True),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        required=True,
    )

    parser.add_argument(
        "--campaign-id",
        required=True,
    )

    parser.add_argument(
        "--model",
        default="gemini-3.1-flash-lite",
    )

    parser.add_argument(
        "--calls",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60,
    )

    parser.add_argument(
        "--budget-usd",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--results-root",
        default=str(
            ROOT
            / "results"
            / "gemini-software-only"
        ),
    )

    parser.add_argument(
        "--history-summary",
        help=(
            "Prior software-only summary used as validated optimizer "
            "history and a cross-campaign duplicate set."
        ),
    )

    args = parser.parse_args()

    if args.calls < 1:
        raise ValueError("--calls must be >= 1")

    if args.repetitions < 1:
        raise ValueError(
            "--repetitions must be >= 1"
        )

    runtime = load_software_runtime(
        Path(args.config)
    )

    pricing = load_pricing(args.model)

    optimizer = GeminiSoftwareOptimizer(
        model=args.model,
        pricing=pricing,
        timeout_seconds=args.timeout_seconds,
        software_repetitions=args.repetitions,
    )

    campaign_dir = (
        Path(args.results_root).resolve()
        / args.campaign_id
    )

    if campaign_dir.exists():
        raise FileExistsError(
            f"Refusing to overwrite: {campaign_dir}"
        )

    campaign_dir.mkdir(parents=True)

    imported = None
    optimizer_history = []
    seen = set()

    if args.history_summary:
        imported = load_history_summary(
            Path(args.history_summary),
            args.repetitions,
        )
        optimizer_history = list(imported["history"])
        seen = set(imported["seen"])

    records = []
    optimizer_events = []

    usage_total = {
        "input_tokens": 0,
        "candidate_tokens": 0,
        "thought_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }

    def save_summary() -> dict:
        """Persist campaign state, including failed Gemini proposals."""

        comparison_records = (
            ([] if imported is None else imported["history"])
            + records
        )
        summary = {
            "campaign_id": args.campaign_id,
            "scope": "software_only",
            "policy": "gemini_api",
            "model": args.model,
            "max_calls": args.calls,
            "repetitions_per_question": args.repetitions,
            "budget_usd": args.budget_usd,
            "usage_total": usage_total,
            "history_summary": (
                None
                if imported is None
                else {
                    "path": imported["path"],
                    "sha256": imported["sha256"],
                    "candidate_count": len(imported["history"]),
                }
            ),
            "optimizer_events": optimizer_events,
            "records": [
                {
                    "candidate_id": item["candidate_id"],
                    "status": item["status"],
                    "software": item["software"],
                    "metrics": item["metrics"],
                    "source": item["source"],
                    **(
                        {"error": item["error"]}
                        if item["status"] == "failed"
                        else {}
                    ),
                }
                for item in comparison_records
            ],
            "comparison": comparison_summary(comparison_records),
        }
        write_json(campaign_dir / "summary.json", summary)
        return summary

    print()
    print("Issue #33 Gemini SW-only optimization")
    print(f"Model:       {args.model}")
    print(f"Max calls:   {args.calls}")
    print(f"Repetitions: {args.repetitions}")
    print(f"Budget:      ${args.budget_usd:.4f}")
    print(f"Results:     {campaign_dir}")
    print(f"Prior candidates: {len(optimizer_history)}")
    print()

    for call_index in range(1, args.calls + 1):

        if (
            usage_total["estimated_cost_usd"]
            >= args.budget_usd
        ):
            print("Budget exhausted.")
            break

        print(
            f"[Gemini {call_index}/{args.calls}] "
            "requesting candidate..."
        )

        try:
            candidate, metadata = optimizer.propose(
                optimizer_history,
                seen,
            )

        except Exception as error:
            metadata = getattr(
                error,
                "optimizer_metadata",
                {},
            )

            event = {
                "call": call_index,
                "status": "proposal_failed",
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
                "metadata": metadata,
            }

            optimizer_events.append(event)

            print(
                "    proposal failed:",
                f"{type(error).__name__}: {error}",
            )

            save_summary()
            continue

        usage = metadata["usage"]

        for field in (
            "input_tokens",
            "candidate_tokens",
            "thought_tokens",
            "output_tokens",
            "total_tokens",
        ):
            usage_total[field] += usage[field]

        usage_total["estimated_cost_usd"] += (
            metadata["estimated_cost_usd"]
        )

        snapshot = Candidate.from_dict(candidate)
        candidate_id = snapshot.candidate_id

        seen.add(candidate_id)

        software = snapshot.config["software"]

        print(
            "    proposed:",
            f"temperature={software['temperature']}",
            f"max_output_tokens="
            f"{software['max_output_tokens']}",
        )

        try:
            result = run_software_candidate(
                snapshot.config,
                runtime=runtime,
            )

            metrics = result["metrics"]

            record = {
                "candidate_id": candidate_id,
                "status": "completed",
                "candidate": snapshot.config,
                "software": software,
                "metrics": metrics,
                "optimizer": metadata,
                "result": result,
            }

            print(
                "    result:",
                f"quality={metrics['answer_quality']:.4f}",
                f"latency_ms={metrics['latency_ms']:.2f}",
            )

        except Exception as error:

            record = {
                "candidate_id": candidate_id,
                "status": "failed",
                "candidate": snapshot.config,
                "software": software,
                "metrics": None,
                "optimizer": metadata,
                "error": software_failure(error),
            }

            print(
                "    runtime failed:",
                f"{type(error).__name__}: {error}",
            )

        record["source"] = "campaign"
        records.append(record)
        optimizer_history.append(record)

        optimizer_events.append(
            {
                "call": call_index,
                "status": "accepted",
                "candidate_id": candidate_id,
                "software": software,
                "metadata": metadata,
            }
        )

        write_json(
            campaign_dir
            / f"candidate-{len(records):02d}.json",
            record,
        )

        save_summary()

    # Always leave a durable record, including zero-acceptance campaigns.
    save_summary()

    print()
    print(
        "Accepted candidates:",
        len(records),
    )

    print(
        "Gemini cost:",
        f"${usage_total['estimated_cost_usd']:.8f}",
    )

    print(
        "Summary:",
        campaign_dir / "summary.json",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
