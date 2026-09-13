# Running and validating

Run commands from the repository root unless stated otherwise. Python 3.10 or newer is declared in `pyproject.toml`. The examples below use the project's `uv` workflow.

## Local environment

```powershell
uv sync --extra dev
```

This installs the declared runtime and test dependencies, including PyYAML. Dependency installation may require network access. No model or simulator is installed by this command.

## Contract checks

```powershell
uv run python scripts/validate_configs.py
uv run python -m pytest -q
git diff --check
```

The validator checks schemas, local references, YAML examples, semantic rules, negative cases and mapping consistency. Passing these checks proves the checked contracts agree; it does not prove model inference, the full CHIA loop, or a gem5 campaign ran.

## Hardware execution

The implemented entrypoint is `gem5/run_attention_experiment.py`. Inspect its arguments without running a simulation:

```powershell
uv run python gem5/run_attention_experiment.py --help
```

A simulation requires Docker, a compatible gem5/toolchain image, and a prepared gem5 source directory. The script defaults to `~/gem5-src`; specify the real path explicitly when different. With these prerequisites prepared, the source-defined invocation is:

```powershell
uv run python gem5/run_attention_experiment.py experiment-contracts/attention-experiments/baseline.attention.yaml --gem5-src C:/path/to/gem5-src
```

Replace the placeholder path. This command builds and executes the workload and writes outputs under `gem5/results/q4-baseline/` by default. It has not been executed as part of this documentation cleanup. See the [hardware README](../gem5/README.md) and [recorded Q4 result](../gem5/baseline-results.md) for hardware-specific context.

## Tutor and full-loop execution

The native tutor configuration remains a draft, and project runner/CHIA adapters still contain `NotImplementedError`. There is no verified end-to-end tutor or CHIA command documented here yet. `scripts/run_experiment.py` and `scripts/run_gem5.py` are scaffold boundaries; use the implemented gem5 entrypoint above for hardware work.
