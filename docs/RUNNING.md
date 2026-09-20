# Running

Install and validate:

```bash
uv sync --frozen --extra dev --extra cluster --extra calibration
uv run python scripts/validate_configs.py
uv run python scripts/run_experiment.py --config experiment-contracts/campaigns/final-burst.yaml --validate-only
uv run pytest -q -m "not scheduling"
```

Run the single deterministic smoke only after the native model server, Ray cluster, gem5 image, and energy image pass preflight:

```bash
export OPENSTAX_LLM_PERMISSION_CONFIRMED=1  # only after permission is confirmed
uv run python scripts/run_experiment.py --config experiment-contracts/campaigns/final-burst.yaml --smoke
```

Run equal pilots in separate result directories:

```bash
uv run python scripts/run_experiment.py --config experiment-contracts/campaigns/final-burst.yaml --method random
uv run python scripts/run_experiment.py --config experiment-contracts/campaigns/final-burst.yaml --method gemini
```

Do not increase the candidate budget until the pilot is reviewed. Existing campaign directories cause a fail-closed error to prevent evidence overwrite.
