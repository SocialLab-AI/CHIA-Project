"""Integration-owned CLI for the deterministic combined loop; run from the repo root."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml
from src.common.candidate import Candidate
from src.orchestration.chia import chia_entrypoint, validate_campaign_config
from src.orchestration.policies import deterministic_candidates


def _set_candidate_budget(config, candidate_budget):
    """Keep the execution count and authoritative stopping limit in lockstep."""
    config["iterations"] = candidate_budget
    config.setdefault("stopping", {})["max_evaluated_candidates"] = candidate_budget


def _set_campaign_id(config, campaign_id):
    """Keep raw runtime artifacts inside the effective campaign evidence root."""
    config["campaign_id"] = campaign_id
    root = Path(config.get("results_root", "results")) / campaign_id
    config["runtime"]["hardware"]["artifacts_root"] = str(root / "gem5")
    config["runtime"]["energy"]["artifacts_root"] = str(root / "energy-work")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--method", choices=("gemini", "random"))
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text()) if args.config else {}
    if args.smoke:
        _set_campaign_id(config, "final-burst-smoke")
        _set_candidate_budget(config, 1)
        config["optimizer"] = {"enabled": False}
    elif args.method:
        _set_campaign_id(config, "final-burst-" + args.method)
        _set_candidate_budget(config, config["study"]["candidate_budget_per_method"])
        if args.method == "random":
            config["optimizer"] = {
                "enabled": True, "policy": "random",
                "max_calls": config["iterations"],
                "seed": config["study"]["random_seed"],
            }
        else:
            config["optimizer"] = {
                "enabled": True, "policy": "gemini_api",
                "model": "gemini-3.1-flash-lite",
                "max_calls": config["iterations"],
                "budget_usd": 10.0,
                "timeout_seconds": 60,
            }
    if args.validate_only:
        checked = validate_campaign_config(config)
        candidates = checked.get("candidates", deterministic_candidates())
        print(
            json.dumps(
                {
                    "validated_candidate_ids": [
                        Candidate.from_dict(c).candidate_id for c in candidates
                    ],
                    "execution": "not_started",
                },
                indent=2,
            )
        )
        return 0
    result = chia_entrypoint(config)
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "experiments"},
            indent=2,
        )
    )
    return 0 if result["state"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
