# Running and validating

Run commands from the repository root unless stated otherwise. Python 3.10 or newer is declared in `pyproject.toml`. No command in this guide downloads a model or simulator image automatically.

## Local environment and review

```powershell
uv sync --extra cluster
uv run pytest -q -m "not scheduling"
uv run python scripts/validate_configs.py
uv run python scripts/run_experiment.py --validate-only
git diff --check
```

The tests and contract validator prove deterministic logic, schemas, examples and mappings. They do not prove that a remote worker, llama.cpp or gem5 is available. The scheduling tests are opt-in because they start real local Ray processes:

```powershell
$env:CHIA_RUN_SCHEDULING_TESTS = "1"
uv run pytest -q tests/test_scheduling.py
```

## Portable cluster configuration

`infra/chia/cluster.yaml` is a portable example containing documentation-only IP addresses and generic paths. Do not commit a real address, username, key path or host-specific installation path.

Set the deployment values in the operator shell:

```bash
export CHIA_HEAD_IP="<control-host-address>"
export CHIA_GEM5_IP="<simulation-worker-address>"
export CHIA_HEAD_USER="<control-host-ssh-user>"
export CHIA_WORKER_USER="<simulation-worker-ssh-user>"
export CHIA_PROJECT_PATH="/absolute/path/to/project"
export CHIA_SSH_KEY="/absolute/path/to/private-key"
export CHIA_HEAD_ENV="/absolute/path/to/control-venv/bin/activate"
export CHIA_WORKER_ENV="/absolute/path/to/worker-venv/bin/activate"

python scripts/render_cluster_config.py \
  --output infra/chia/cluster.local.yaml
```

The renderer validates the addresses, unprivileged usernames and absolute paths. It writes only an ignored `*.local.yaml` file and never reads private-key contents or contacts a host. Review the generated file before starting the cluster:

```bash
chia up infra/chia/cluster.local.yaml
```

The control host advertises `control` and `llama_cpp`. The simulation worker advertises `gem5`. CHIA/Ray schedules nodes by these labels; simulated CPU cores are independent of Ray CPU reservations.

## Runtime prerequisites

The control host requires:

- the project environment with the locked CHIA/Ray dependencies;
- the exact configured Qwen GGUF;
- a compatible llama.cpp build and loopback-only server;
- the configured OpenStax evaluation files.

The simulation worker requires:

- the project environment with CHIA/Ray;
- Docker access for a trusted worker account;
- the pinned gem5/toolchain image already installed.

The project preflights model hash, build identity, context capacity, parallel slots and container identity. Credentials belong in environment variables. They must not appear in campaign YAML, generated records or shared logs.

## Full-loop campaign

Copy the portable campaign and edit the ignored copy for the deployment:

```bash
cp experiment-contracts/testing/full-loop.local.example.yaml \
  experiment-contracts/testing/full-loop.server.local.yaml
```

Choose a unique campaign ID. For distributed execution, set `mode: chia` and select the approved tier/backend pair. Set the loopback llama.cpp endpoint, model directory, GGUF filename, SHA-256, context capacity, parallel slots, timeouts and reviewed numerical tolerance. Validate the complete campaign without connecting to Ray:

```bash
python scripts/run_experiment.py \
  --config experiment-contracts/testing/full-loop.server.local.yaml \
  --validate-only
```

Then execute the campaign:

```bash
python scripts/run_experiment.py \
  --config experiment-contracts/testing/full-loop.server.local.yaml
```

The controller validates and maps each candidate, runs native Qwen and gem5 nodes, verifies their results, writes one combined record, and applies deterministic stopping rules. See [FULL_LOOP.md](FULL_LOOP.md) for node ownership, retry behavior, logging, security and record semantics.

## Proxy-fidelity experiment

Issue #60 uses a separate protocol because native prompt processing and a one-layer attention microbenchmark have different measurement scopes. Follow [the proxy-fidelity protocol](experiments/proxy-fidelity.md) and read the [calibration decision and developer handoff](experiments/proxy-calibration-handoff.md) before changing the kernel dimensions or numerical tolerance.

Run profile, native, hardware and analysis phases separately so expensive simulation work can be resumed without repeating completed measurements. Generated evidence belongs under the configured ignored results directory. Preserve earlier bundles instead of rewriting them after a proxy change.

## Result interpretation

- Native llama.cpp latency and quality are application metrics.
- gem5 simulated seconds, instructions, IPC and cache misses are proxy metrics.
- Simulator host wall time is an execution-cost metric.
- Numerical error checks the Q4 proxy against its FP32 kernel reference.

A successful distributed run proves that the nodes executed and produced validated records. It does not prove that the attention proxy predicts full-model latency or educational quality.
