# Running

Install and validate:

```bash
uv sync --frozen --extra dev --extra cluster --extra calibration
uv run python scripts/validate_configs.py
uv run python scripts/run_experiment.py --config experiment-contracts/campaigns/final-burst.yaml --validate-only
uv run pytest -q -m "not scheduling"
```

Run the fail-closed deployment preflight from the CHIA head node before any
smoke, pilot, or migrated-server campaign:

```bash
export OPENSTAX_LLM_PERMISSION_CONFIRMED=1  # only after permission is confirmed
uv run python scripts/preflight_release.py --config experiment-contracts/campaigns/final-burst.yaml
```

This checks the reviewed local GGUF and live llama.cpp identity, required Ray
resources, worker Python/uv/Docker availability, both pinned container images,
and a short synthetic Accelergy energy-estimation round trip. It does not run
gem5, call Gemini, or create campaign evidence.

Before starting Ray, every cluster machine must report the same Python and Ray
versions. A campaign started with `uv run` also requires `uv` on the `PATH`
inherited by every raylet. On the gem5 worker, verify:

```bash
command -v uv
uv --version
python --version
ray --version
docker version
```

If `command -v uv` fails, install `uv`, add its installation directory to
`PATH`, and restart the gem5 raylet from that shell. The head node passes the
OpenStax attestation into the Ray job environment; it does not need to be stored
on the worker.

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
