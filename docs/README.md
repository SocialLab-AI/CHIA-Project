# CHIA Project Documentation

This directory contains the reviewed project documentation for the CHIA hackathon project.

## Current project

- **Application:** Offline AI Tutor
- **Proxy workload:** `AttentionKernelQuantizedKV`
- **Simulation:** gem5 / RISC-V
- **Orchestration:** CHIA
- **Current baseline:** `RiscvTimingSimpleCPU`, 1 core, 1 GHz, 16 KiB L1D, 256 KiB L2, FP32 KV cache, context length 512

## Current source of truth

- [`decisions/current-project-state.md`](decisions/current-project-state.md) — current thesis, verified baseline, active search space, fixed/deferred parameters, compute policy, and open questions.
- [`experiments/README.md`](experiments/README.md) — experiment evidence organization and recording rules.
- [`experiments/baselines/fp32-attention-kv-cache.md`](experiments/baselines/fp32-attention-kv-cache.md) — measured FP32 attention/KV-cache gem5 baseline.

## Documentation states

- **Canonical** — current team source of truth.
- **Working** — actively changing design or research.
- **Evidence** — measured run/report; do not rewrite historical results to match newer expectations.
- **Archived** — superseded or rejected direction retained outside the canonical documentation set when traceability is useful.

## Rule

Before creating a new document, check whether the topic already has a canonical document. Prefer updating or consolidating an existing document rather than creating a parallel explanation.

## Planned documentation

The following topics are being reviewed before they become canonical repository documentation:

- attention proxy decision and rationale
- attention/gem5 knobs, metrics, and constraints
- experiment contracts architecture
- CHIA/gem5 runtime setup
- experiment methodology and final results
