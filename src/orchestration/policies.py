"""Deterministic candidate/decision policies.

The software-only policy exhaustively covers the reviewed Tutor software
design space while keeping hardware, workload, model, and runtime settings
fixed.

The existing mixed HW/SW deterministic policy is retained for the full loop.
"""

import copy

import yaml

from src.common.candidate import ROOT, baseline_candidate


def deterministic_software_candidates():
    """Return every reviewed software-only candidate exactly once.

    Only the fields listed in active_candidates are varied. Everything else
    comes from baseline_candidate() and is kept fixed.

    Current grid:
        temperature       = [0.0, 0.2, 0.5]
        max_output_tokens = [128, 256, 384]

    Therefore this currently produces 3 x 3 = 9 candidates.
    """
    path = (
        ROOT
        / "experiment-contracts"
        / "testing"
        / "software-design-space.yaml"
    )

    design = yaml.safe_load(path.read_text(encoding="utf-8"))
    active = design["active_candidates"]

    candidates = []

    for temperature in active["temperature"]:
        for max_output_tokens in active["max_output_tokens"]:
            candidate = copy.deepcopy(baseline_candidate())

            candidate["software"]["temperature"] = temperature
            candidate["software"]["max_output_tokens"] = max_output_tokens

            candidates.append(candidate)

    return candidates


def deterministic_candidates():
    """Existing deterministic mixed HW/SW candidates for the full loop."""
    first = baseline_candidate()

    second = copy.deepcopy(first)
    second["software"]["max_output_tokens"] = 128
    second["hardware"]["l1d_cache_kib"] = 32

    third = copy.deepcopy(first)
    third["software"]["temperature"] = 0.2
    third["hardware"]["issue_width"] = 1

    return [first, second, third]


def pareto(records):
    """Compare within the same profile/context only.

    All values stored in evaluation.objectives are minimization objectives.
    Native time and proxy simulation time therefore remain separate.
    """
    eligible = [
        record
        for record in records
        if record["status"] == "completed"
        and record["evaluation"]["feasible"]
    ]

    frontier = []

    for candidate in eligible:
        target = candidate["evaluation"]
        dominated = False

        for other in eligible:
            value = other["evaluation"]

            if value["comparison_group"] != target["comparison_group"]:
                continue

            keys = target["objectives"]

            if (
                all(
                    value["objectives"][key]
                    <= target["objectives"][key]
                    for key in keys
                )
                and any(
                    value["objectives"][key]
                    < target["objectives"][key]
                    for key in keys
                )
            ):
                dominated = True
                break

        if not dominated:
            frontier.append(candidate["candidate_id"])

    return frontier
