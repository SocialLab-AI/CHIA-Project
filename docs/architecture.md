# Project Architecture

The project uses `experiment-contracts/` as the canonical configuration and schema layer.

```text
                       CHIA orchestration
                              |
                    canonical experiment
                       configuration
                              |
              +---------------+---------------+
              |                               |
              v                               v
        Tutor Adapter                  Hardware Adapter
         (planned)                         |
              |                            v
      model/runtime TBD              gem5 experiment runner
              |                            |
              v                            v
       quality metrics               hardware metrics
              |                            |
              +---------------+------------+
                              |
                              v
                         Run Record
```

## Current implementation status

### Canonical contracts

Implemented under `experiment-contracts/`.

This is the single source of truth for experiment configuration, hardware
parameters, workload settings, measurement settings, and run records.

### Hardware execution

Implemented under `gem5/`.

The gem5 experiment runner consumes the canonical experiment contract,
builds the attention workload, configures gem5, executes the simulation,
and extracts hardware metrics.

### `src/` package

The `src/` package defines stable adapter and orchestration boundaries.
Some modules intentionally remain skeletons while their implementations
are developed.

### Tutor runtime

The tutor runtime, model adapter, evaluator, and software-side metrics are
currently planned. The final software design is still being defined.

Reference material is used for evaluation only and is not automatically
provided to the tutor as retrieval context.
