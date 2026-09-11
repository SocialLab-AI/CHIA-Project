# CHIA Project Documentation

This directory contains the reviewed project documentation for the CHIA hackathon project.

## Current project

- **Application:** Offline AI Tutor
- **Proxy workload:** Attention kernel with packed Q4 KV cache
- **Simulation:** gem5 / RISC-V
- **Orchestration:** CHIA
- **Verified baseline:** `RiscvO3CPU`, 2 cores, 1 GHz, issue width 2, 64 KiB L1D, 1024 KiB shared L2, Q4 KV cache, context length 512

## Current source of truth

- [`decisions/current-project-state.md`](decisions/current-project-state.md) — current thesis, verified baseline, active search space, fixed/deferred parameters, implementation status, compute policy, and open questions.
- [`architecture.md`](architecture.md) — project-level architecture and implementation boundaries.
- [`experiments/README.md`](experiments/README.md) — experiment evidence organization and recording rules.
- [`../experiment-contracts/`](../experiment-contracts/) — canonical schemas, experiment contracts, design space, compute policy, and run-record definitions.

## Historical evidence

- [`experiments/baselines/fp32-attention-kv-cache.md`](experiments/baselines/fp32-attention-kv-cache.md) — earlier measured FP32 attention/KV-cache gem5 baseline.

Historical experiment records are preserved as evidence and are not rewritten to match newer validated configurations.

## Documentation states

- **Canonical** — current team source of truth.
- **Working** — actively changing design or research.
- **Evidence** — measured run/report; historical results remain unchanged.
- **Archived** — superseded or rejected direction retained when traceability is useful.

## Rule

Before creating a new document, check whether the topic already has a canonical document. Prefer updating or consolidating an existing document rather than creating a parallel explanation.

## Still to document

The following areas are still evolving:

- final tutor runtime and software search space
- tutor-to-attention proxy mapping
- CHIA orchestration integration
- final evaluation methodology and Pareto objectives
- final campaign results
