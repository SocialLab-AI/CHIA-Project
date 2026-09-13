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

## Four Contracts, Four Responsibilities

| Contract | Question answered |
|---|---|
| AI Tutor config | What application configuration are we evaluating? |
| Attention experiment/design space | What proxy workload and simulated architecture are we evaluating? |
| Compute policy | Where and at what scale may the real job execute? |
| Run record | What actually happened and what evidence was produced? |

## Separation That Must Remain Explicit

- `hardware.*` inside an attention experiment describes the **simulated target architecture** in gem5.
- `execution.backend` inside a run record and the compute policy describes the **real host/backend** running CHIA/gem5.
- Those are different layers and must never be conflated.

## CHIA Control and Guardrails

CHIA may propose values only from the active design space. Deterministic validation checks legality before execution.

Gemini may propose candidates, but it must not:
- authorize a higher compute tier,
- enable organizer burst outside the final tier,
- invent unsupported knob values,
- bypass schema or semantic validation.

## Current Implementation Status

### Canonical Contracts
Implemented under `experiment-contracts/`.
This is the single source of truth for experiment configuration, hardware parameters, workload settings, measurement settings, and run records.

### Hardware Execution
Implemented under `gem5/`.
The gem5 experiment runner consumes the canonical experiment contract, builds the attention workload, configures gem5, executes the simulation, and extracts hardware metrics.

### `src/` Package
The `src/` package defines stable adapter and orchestration boundaries:
- `src.hardware.runner.run_hardware(config)` delegates to the executable gem5 pipeline.
- `src.tutor.runner.run_tutor(config)` defines the entrypoint for the tutor application.
- `src.orchestration.experiment.run_experiment(config)` coordinates execution of both domains.
Some adapter modules intentionally remain skeletons while their implementations are developed.

### Tutor Runtime
The tutor runtime, model adapter, evaluator, and software-side metrics are currently planned. The baseline configuration is specified with Llama 3.2 1B Instruct and a MiniLM-L6-dot-v1 RAG pipeline, with software search space pending definition.

Reference material (`data/references/openstax.json`) is strictly held out for evaluation only and is never provided to the tutor as retrieval context.
