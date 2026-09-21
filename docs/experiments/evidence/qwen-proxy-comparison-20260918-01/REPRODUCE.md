# Reproducing the Qwen proxy comparison

This guide contains the complete command sequence needed to repeat the Issue
#60 experiment. Run commands from the repository root unless a step says
otherwise. Replace every angle-bracket placeholder with a reviewed deployment
value. Never commit private keys, local YAML overlays, model files or API keys.

The recorded run compared two corrected profiles:

```text
original-corrected: 4 query heads / 2 KV heads / dimension 32
qwen-shaped:       14 query heads / 2 KV heads / dimension 64
contexts:          128, 256, 512, 1024, 2048
trials:            3 per profile/context
total gem5 jobs:   30
```

The experiment does not use Gemini and does not run a complete LLM in gem5.

## 1. Create an isolated checkout

Do not use a CHIA-synchronized `/tmp/chia-project` directory as a development
checkout.

```bash
git clone https://github.com/SocialLab-AI/CHIA-Project.git CHIA-Project
cd CHIA-Project
git fetch origin
git switch --track origin/issue-60-proxy-fidelity
git rev-parse HEAD
```

For the recorded implementation, the history must contain these commits:

```text
ebbd7c5  Calibrate Qwen attention proxy comparison
8dd76bf  Record repeated proxy comparison evidence
```

## 2. Create the Python environment

Python 3.10 or newer, `uv`, Docker, CHIA/Ray and the calibration reader are
required. The gem5 worker must already contain the pinned gem5 image.

```bash
uv sync --extra cluster --extra calibration
uv run python --version
uv run python scripts/validate_configs.py
uv run pytest -q -m "not scheduling"
docker image inspect ghcr.io/gem5/devcontainer:v25-1 >/dev/null
```

The two scheduling tests are intentionally opt-in. The native C tests run when
`gcc` is present and skip otherwise.

## 3. Provide the exact native model tools

Supply the selected GGUF and an existing compatible `llama-bench` executable.
The repository does not download either artifact automatically.

```bash
export MODEL_FILE="<absolute-path>/qwen2.5-0.5b-instruct-q5_k_m.gguf"
export LLAMA_BENCH="<absolute-path>/llama-bench"

test -f "$MODEL_FILE"
test -x "$LLAMA_BENCH"
sha256sum "$MODEL_FILE"
```

The expected model digest is:

```text
041474553fcabfc2a2d67903f9d2c2e50bd92528e670da4f33b5d0ce6e59fd55
```

Do not confuse Q5_K_M weight quantization with KV-cache quantization. The
recorded native benchmark reported F16 keys and F16 values.

## 4. Compile both proxy choices natively

These commands verify that the preserved entry files compile, execute every
head and report grouped-query mapping before simulator time is spent.

```bash
mkdir -p /tmp/chia-proxy-native-check

gcc -O2 -std=c11 -pthread \
  -DCONTEXT=16 \
  gem5/attention_kv_original_proxy.c \
  -lm -o /tmp/chia-proxy-native-check/original

gcc -O2 -std=c11 -pthread \
  -DCONTEXT=16 \
  gem5/attention_kv_qwen_proxy.c \
  -lm -o /tmp/chia-proxy-native-check/qwen-shaped

/tmp/chia-proxy-native-check/original
/tmp/chia-proxy-native-check/qwen-shaped
```

Both commands must report:

```text
kv_mapping=grouped_query
repetitions=1
status=PASS
```

`status=PASS` means the numerical outputs are finite. External validation
decides whether the configured absolute tolerances pass.

## 5. Create the private CHIA cluster overlay

The tracked `infra/chia/cluster.yaml` contains documentation-only addresses.
Always render and use the ignored `cluster.local.yaml` for a real deployment.

```bash
export CHIA_HEAD_IP="<control-host-address>"
export CHIA_GEM5_IP="<gem5-worker-address>"
export CHIA_HEAD_USER="<control-user>"
export CHIA_WORKER_USER="<worker-user>"
export CHIA_PROJECT_PATH="$(pwd)/"
export CHIA_SSH_KEY="<absolute-path-to-private-key>"
export CHIA_HEAD_ENV="<absolute-path-to-control-venv>/bin/activate"
export CHIA_WORKER_ENV="<absolute-path-to-worker-venv>/bin/activate"

uv run python scripts/render_cluster_config.py \
  --output infra/chia/cluster.local.yaml

cat infra/chia/cluster.local.yaml
uv run chia up infra/chia/cluster.local.yaml
```

Do not restart a shared cluster while another campaign is running. Startup must
show source synchronization to both the control host and gem5 worker.

## 6. Verify the synchronized worker code

```bash
uv run python - <<'PY'
import inspect
import ray
from chia.base.ChiaFunction import ChiaFunction

ray.init(address="auto")

def probe_worker():
    from src.common.candidate import Candidate, ROOT
    from src.hardware.runner import run_gem5_candidate

    return {
        "project_root": str(ROOT),
        "candidate_signature": str(inspect.signature(Candidate.from_dict)),
        "calibration_mode_present": (
            "calibration_mode" in inspect.getsource(run_gem5_candidate)
        ),
    }

remote_probe = ChiaFunction(
    resources={"gem5": 1},
    num_cpus=1,
    max_retries=0,
)(probe_worker)

print(ray.get(remote_probe.chia_remote(), timeout=60))
PY
```

Required evidence:

```text
project_root: /tmp/chia-project
candidate_signature: (value, *, calibration=False)
calibration_mode_present: True
```

Stop if the worker reports the old signature. Resynchronize before running the
experiment.

## 7. Generate or verify the native evidence

Copy the portable fidelity configuration:

```bash
cp experiment-contracts/testing/proxy-fidelity.server.example.yaml \
  experiment-contracts/testing/proxy-fidelity.server.local.yaml
```

Edit the ignored local file and set:

```text
experiment_id
native.model_path
native.llama_bench
hardware mode and Ray address
```

Keep the recorded model SHA, contexts, threads, repetitions and reviewed
absolute tolerances unless the new experiment explicitly studies a different
protocol.

Run the native phases:

```bash
uv run python -m scripts.run_proxy_fidelity \
  --config experiment-contracts/testing/proxy-fidelity.server.local.yaml \
  --phase profile

uv run python -m scripts.run_proxy_fidelity \
  --config experiment-contracts/testing/proxy-fidelity.server.local.yaml \
  --phase native
```

The evidence directory must now contain:

```text
results/proxy-fidelity/<fidelity-experiment-id>/model-profile.json
results/proxy-fidelity/<fidelity-experiment-id>/native-context-sweep.json
```

The recorded comparison reused the already completed native sweep rather than
rerunning it for each proxy profile.

## 8. Prepare and validate the repeated comparison

```bash
cp experiment-contracts/testing/proxy-comparison.server.example.yaml \
  experiment-contracts/testing/proxy-comparison.server.local.yaml
```

Edit the local file:

```text
experiment_id: choose a new unique identifier
native_evidence_directory: point to the completed fidelity evidence directory
hardware.mode: chia
hardware.ray_address: auto
```

Validate without submitting Ray work:

```bash
uv run python -m scripts.run_proxy_comparison \
  --config experiment-contracts/testing/proxy-comparison.server.local.yaml \
  --validate-only
```

Expected plan:

```text
contexts: 128, 256, 512, 1024, 2048
trials_per_context: 3
planned_hardware_jobs: 30
native_kv_cache_types: key=f16, value=f16
validation: passed
execution: not_started
```

## 9. Run or resume the 30-job comparison

```bash
set -o pipefail

uv run python -m scripts.run_proxy_comparison \
  --config experiment-contracts/testing/proxy-comparison.server.local.yaml \
  2>&1 | tee /tmp/qwen-proxy-comparison.log
```

Every successful job is recorded in `checkpoint.json`. If the terminal or
driver stops, rerun the exact same command with the same experiment ID. Matching
completed cases resume instead of executing again.

Successful completion prints:

```json
{
  "experiment_id": "<comparison-experiment-id>",
  "status": "completed"
}
```

## 10. Inspect and verify the result bundle

```bash
export RESULTS="results/proxy-comparison/<comparison-experiment-id>"

find "$RESULTS" -maxdepth 1 -type f -print
cat "$RESULTS/REPORT.md"
uv run python -m json.tool "$RESULTS/proxy-comparison.json" >/dev/null
uv run python -m json.tool "$RESULTS/checkpoint.json" >/dev/null
uv run python -m json.tool "$RESULTS/SHA256SUMS.json"
```

Recalculate the artifact hashes:

```bash
sha256sum \
  "$RESULTS/REPORT.md" \
  "$RESULTS/checkpoint.json" \
  "$RESULTS/normalized-context-trends-original-corrected.svg" \
  "$RESULTS/normalized-context-trends-qwen-shaped.svg" \
  "$RESULTS/proxy-comparison.json"
```

A new run may have different JSON/checkpoint hashes because run IDs, timestamps,
host provenance and artifact paths change. Compare scientific fields and the
new run's own manifest. Do not expect every new run to reproduce the historical
artifact hashes byte-for-byte.

## 11. Archive evidence safely

The recorded run's safe, checksum-matching `REPORT.md`, SVG plots and
`SHA256SUMS.json` are stored in this directory. `checkpoint.json` and
`proxy-comparison.json` include detailed per-trial runtime provenance and remain
deployment-local. Before publishing raw JSON, inspect it for hostnames,
addresses, user paths and other deployment data.

To prepare a private review copy without staging unrelated work:

```bash
export EVIDENCE_DIR="docs/experiments/evidence/<comparison-experiment-id>"
mkdir -p "$EVIDENCE_DIR"

cp "$RESULTS/REPORT.md" "$EVIDENCE_DIR/"
cp "$RESULTS/normalized-context-trends-original-corrected.svg" "$EVIDENCE_DIR/"
cp "$RESULTS/normalized-context-trends-qwen-shaped.svg" "$EVIDENCE_DIR/"

git status --short
git add -- "$EVIDENCE_DIR"
git diff --cached --check
```

Do not use `git add .` on a shared checkout. Raw logs should be attached to a
private experiment record or artifact store after review rather than committed
with machine-specific output.

## 12. Interpret within the supported claim

The supported statement is:

> The corrected one-layer gem5 attention proxies reproducibly follow native
> Qwen context-growth trends. The Qwen-shaped profile is structurally closer to
> the selected model, while KV-format alignment, numerical acceptance and final
> team selection remain unresolved.

Do not claim that gem5 executed complete Qwen, that proxy seconds predict full
inference latency, or that gem5 hardware rankings have been reproduced on
equivalent native hardware.
