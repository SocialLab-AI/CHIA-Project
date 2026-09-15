"""Deterministic candidate/decision policies; orchestration owns stopping and Pareto logic."""

import copy
from src.common.candidate import baseline_candidate


def deterministic_candidates():
    first = baseline_candidate()
    second = copy.deepcopy(first)
    second["software"]["max_output_tokens"] = 64
    second["hardware"]["l1d_cache_kib"] = 32
    third = copy.deepcopy(first)
    third["software"]["temperature"] = 0.2
    third["hardware"]["issue_width"] = 1
    return [first, second, third]


def pareto(records):
    """Compare within the same profile/context only; native and proxy time stay separate."""
    eligible = [
        r for r in records if r["status"] == "completed" and r["evaluation"]["feasible"]
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
            if all(
                value["objectives"][k] <= target["objectives"][k] for k in keys
            ) and any(value["objectives"][k] < target["objectives"][k] for k in keys):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate["candidate_id"])
    return frontier
