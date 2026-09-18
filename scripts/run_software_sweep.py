#!/usr/bin/env python3
"""Run the Issue #33 native Qwen software-only optimization sweep.

This deliberately bypasses gem5 and the hardware node.

It uses the same:
- canonical Candidate validation
- Qwen/llama.cpp runtime adapter
- OpenStax evaluation
- software metrics

that the integrated CHIA loop uses.

Modes:
    smoke -> 3 representative candidates
    full  -> all reviewed software candidates
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from statistics import mean

import yaml

from src.common.candidate import Candidate, ROOT
from src.orchestration.policies import deterministic_software_candidates
from src.tutor.runner import run_software_candidate


SMOKE_CONFIGS = {
    (0.0, 384),  # current baseline
    (0.0, 128),  # isolate output-length effect
    (0.5, 256),  # exercise non-zero sampling temperature
}


def load_runtime(path: Path) -> dict:
    """Load only the native software runtime from a local campaign config."""
    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(config, dict):
        raise ValueError("Campaign configuration must be a YAML object.")

    runtime = config.get("runtime", {}).get("software")

    if not isinstance(runtime, dict):
        raise ValueError(
            "Campaign config must contain runtime.software."
        )

    return copy.deepcopy(runtime)


def select_candidates(mode: str) -> list[dict]:
    candidates = deterministic_software_candidates()

    if mode == "full":
        return candidates

    selected = []

    for candidate in candidates:
        software = candidate["software"]

        key = (
            float(software["temperature"]),
            int(software["max_output_tokens"]),
        )

        if key in SMOKE_CONFIGS:
            selected.append(candidate)

    if len(selected) != len(SMOKE_CONFIGS):
        raise RuntimeError(
            "Smoke candidates are not all present in the reviewed design space."
        )

    return selected


def pareto_candidate_ids(records: list[dict]) -> list[str]:
    """Pareto frontier for SW-only quality/latency optimization.

    Better means:
        answer_quality: higher
        latency_ms:     lower
    """
    completed = [
        record
        for record in records
        if record["status"] == "completed"
    ]

    frontier = []

    for target in completed:
        tq = target["metrics"]["answer_quality"]
        tl = target["metrics"]["latency_ms"]

        dominated = False

        for other in completed:
            if other is target:
                continue

            oq = other["metrics"]["answer_quality"]
            ol = other["metrics"]["latency_ms"]

            at_least_as_good = oq >= tq and ol <= tl
            strictly_better = oq > tq or ol < tl

            if at_least_as_good and strictly_better:
                dominated = True
                break

        if not dominated:
            frontier.append(target["candidate_id"])

    return frontier


def diagnostic_metrics(result: dict) -> dict:
    """Extract convenient secondary metrics from per-question samples."""
    samples = result["samples"]

    completion_tokens = [
        sample["completion_tokens"]
        for sample in samples
    ]

    generation_tps = [
        sample["generation_tokens_per_second"]
        for sample in samples
    ]

    generation_latency = [
        sample["generation_latency_ms"]
        for sample in samples
    ]

    return {
        "mean_completion_tokens": mean(completion_tokens),
        "mean_generation_tokens_per_second": mean(generation_tps),
        "mean_generation_latency_ms": mean(generation_latency),
    }


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


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        required=True,
        help="Local campaign YAML containing runtime.software.",
    )

    parser.add_argument(
        "--mode",
        choices=("smoke", "full"),
        default="smoke",
    )

    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--campaign-id",
        required=True,
    )

    parser.add_argument(
        "--results-root",
        default=str(ROOT / "results" / "software-only"),
    )

    args = parser.parse_args()

    if args.repetitions < 1:
        raise ValueError("--repetitions must be >= 1")

    runtime = load_runtime(Path(args.config))

    campaign_dir = (
        Path(args.results_root).resolve()
        / args.campaign_id
    )

    if campaign_dir.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing campaign: {campaign_dir}"
        )

    campaign_dir.mkdir(parents=True)

    candidates = select_candidates(args.mode)

    records = []

    print()
    print("Issue #33 software-only optimization")
    print(f"Mode:        {args.mode}")
    print(f"Candidates:  {len(candidates)}")
    print(f"Repetitions: {args.repetitions}")
    print(f"Results:     {campaign_dir}")
    print()

    for index, original in enumerate(candidates, start=1):
        candidate = copy.deepcopy(original)

        candidate["measurement"]["software_repetitions"] = (
            args.repetitions
        )

        # Full canonical/schema/design-space validation before runtime access.
        snapshot = Candidate.from_dict(candidate)

        software = snapshot.config["software"]

        print(
            f"[{index}/{len(candidates)}] "
            f"temperature={software['temperature']} "
            f"max_output_tokens={software['max_output_tokens']}"
        )

        try:
            result = run_software_candidate(
                snapshot.config,
                runtime=runtime,
            )

            metrics = {
                **result["metrics"],
                **diagnostic_metrics(result),
            }

            record = {
                "candidate_id": snapshot.candidate_id,
                "status": "completed",
                "software": software,
                "metrics": metrics,
                "result": result,
            }

            print(
                "    "
                f"quality={metrics['answer_quality']:.4f} "
                f"median_latency_ms={metrics['latency_ms']:.2f} "
                f"mean_completion_tokens="
                f"{metrics['mean_completion_tokens']:.1f}"
            )

        except Exception as error:
            record = {
                "candidate_id": snapshot.candidate_id,
                "status": "failed",
                "software": software,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }

            print(
                f"    FAILED: "
                f"{type(error).__name__}: {error}"
            )

        records.append(record)

        write_json(
            campaign_dir / f"candidate-{index:02d}.json",
            record,
        )

    pareto_ids = pareto_candidate_ids(records)

    summary_records = []

    for record in records:
        compact = {
            "candidate_id": record["candidate_id"],
            "status": record["status"],
            "software": record["software"],
        }

        if record["status"] == "completed":
            compact["metrics"] = record["metrics"]
        else:
            compact["error"] = record["error"]

        summary_records.append(compact)

    summary = {
        "campaign_id": args.campaign_id,
        "scope": "software_only",
        "mode": args.mode,
        "repetitions_per_question": args.repetitions,
        "candidate_count": len(records),
        "completed_count": sum(
            record["status"] == "completed"
            for record in records
        ),
        "failed_count": sum(
            record["status"] == "failed"
            for record in records
        ),
        "objectives": {
            "answer_quality": "maximize",
            "latency_ms": "minimize",
        },
        "pareto_candidate_ids": pareto_ids,
        "records": summary_records,
    }

    write_json(
        campaign_dir / "summary.json",
        summary,
    )

    print()
    print(
        f"Completed: {summary['completed_count']} / "
        f"{summary['candidate_count']}"
    )
    print(f"Pareto candidates: {len(pareto_ids)}")
    print(f"Summary: {campaign_dir / 'summary.json'}")

    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
