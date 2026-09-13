# CHIA Experiment Contracts

Canonical configuration and contract layer for the CHIA offline AI Tutor project.

## Contract Domains

The repository consolidates all configuration contracts under `experiment-contracts/`:

- `ai-tutor-config/` — application-level AI Tutor configuration, software baseline, and design space.
- `attention-experiments/` — concrete gem5 attention proxy experiments and active hardware design space.
- `compute-policy/` — host execution tiers, backend environments, parallelism, and compute governance.
- `run-records/` — verifiable evidence records of actual executions.
- `schemas/` — shared schema definitions (`shared.schema.json`).

## Four Contracts, Four Responsibilities

| Contract | Question answered |
|---|---|
| AI Tutor config | What application configuration are we evaluating? |
| Attention experiment/design space | What proxy workload and simulated architecture are we evaluating? |
| Compute policy | Where and at what scale may the real job execute? |
| Run record | What actually happened and what evidence was produced? |

## Separation That Must Remain Explicit

- `hardware.*` inside an attention experiment describes the **simulated target architecture** in gem5.
- `execution.backend` inside a run record and compute policy describes the **real host/backend** running CHIA/gem5.
- Those are different layers and must never be conflated.

## Data Flow

```text
AI Tutor config
      |
      v
Tutor -> attention mapping (proxy bridge)
      |
      v
Attention design space ----> CHIA proposes candidate
                                |
                                v
                        Attention experiment
                                |
                       compute policy gate
                                |
                                v
                           CHIA / gem5
                                |
                                v
                            Run record
```

## Validation

Validation is driven by the root validation entrypoint:

```bash
python scripts/validate_configs.py
```

This verifies schema validity, composed local references, domain documents, and policy constraints.

## Important Rule

JSON-schema validity means a document is structurally valid. It does **not** prove that a future/planned knob is already implemented in the kernel or mapped to gem5. Execution readiness (`runtime_ready: true`) requires verified runtime adapters and model artifacts.
