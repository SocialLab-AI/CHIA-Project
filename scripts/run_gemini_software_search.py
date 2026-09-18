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
import json
from pathlib import Path

import yaml

from src.common.candidate import Candidate, ROOT
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

    history = []
    seen = set()
    optimizer_events = []

    usage_total = {
        "input_tokens": 0,
        "candidate_tokens": 0,
        "thought_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }

    print()
    print("Issue #33 Gemini SW-only optimization")
    print(f"Model:       {args.model}")
    print(f"Max calls:   {args.calls}")
    print(f"Repetitions: {args.repetitions}")
    print(f"Budget:      ${args.budget_usd:.4f}")
    print(f"Results:     {campaign_dir}")
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
                history,
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

        history.append(record)

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
            / f"candidate-{len(history):02d}.json",
            record,
        )

        summary = {
            "campaign_id": args.campaign_id,
            "scope": "software_only",
            "policy": "gemini_api",
            "model": args.model,
            "max_calls": args.calls,
            "repetitions_per_question": (
                args.repetitions
            ),
            "budget_usd": args.budget_usd,
            "usage_total": usage_total,
            "optimizer_events": optimizer_events,
            "records": [
                {
                    "candidate_id": item[
                        "candidate_id"
                    ],
                    "status": item["status"],
                    "software": item["software"],
                    "metrics": item["metrics"],
                    **(
                        {"error": item["error"]}
                        if item["status"] == "failed"
                        else {}
                    ),
                }
                for item in history
            ],
        }

        write_json(
            campaign_dir / "summary.json",
            summary,
        )

    print()
    print(
        "Accepted candidates:",
        len(history),
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
