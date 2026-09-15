"""Integration-owned CLI for the deterministic combined loop; run from the repo root."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml
from src.common.candidate import Candidate
from src.orchestration.chia import chia_entrypoint
from src.orchestration.policies import deterministic_candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text()) if args.config else {}
    if args.validate_only:
        candidates = config.get("candidates", deterministic_candidates())
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
