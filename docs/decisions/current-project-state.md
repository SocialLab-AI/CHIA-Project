# Current Project State

## Current thesis

Build an offline AI Tutor experiment where CHIA orchestrates software/hardware
co-design. gem5 executes a representative attention workload with a packed Q4
KV cache as the hardware proxy for LLM inference behavior.

The current verified baseline is the two-core Q4 attention workload. The initial
hardware search space is defined in `experiment-contracts/`, while the broader
software search space is still being finalized.

## Current verified baseline

| Parameter | Value |
| --- | --- |
| CPU | `RiscvO3CPU` |
| Cores | 2 |
| Frequency | 1 GHz |
| Issue width | 2 |
| L1 I-cache | 16 KiB, 2-way, 2-cycle latency |
| L1 D-cache | 64 KiB, 4-way, 2-cycle latency |
| L2 cache | 1024 KiB, 8-way, 20-cycle latency |
| Memory | `DDR3_1600_8x8` |
| Memory size | 16 MiB |
| Execution mode | SE |
| Context length | 512 |
| Query heads | 4 |
| KV heads | 2 |
| Head dimension | 32 |
| Layers | 1 |
| Software threads | 2 |
| Repetitions | 10 |
| Warmup runs | 0 |
| KV format | packed Q4 |

## Active initial hardware search space

The canonical values are defined in
`experiment-contracts/attention-experiments/design-space.yaml`.

Active hardware candidates:

- CPU model: `RiscvTimingSimpleCPU` / `RiscvO3CPU`
- Frequency: 1 / 2 / 3 / 4 GHz
- Issue width: 1 / 2 / 4
- L1 D-cache: 16 / 32 / 64 KiB
- L1 D-cache associativity: 2 / 4 / 8
- L2 cache: 256 / 512 / 1024 KiB
- L2 associativity: 4 / 8 / 16

`RiscvTimingSimpleCPU` requires issue width 1.

Context length 128 / 256 / 512 is an evaluation axis rather than a hardware
optimization knob.

## Fixed for the initial campaign

- Cores: 2
- L1 I-cache: 16 KiB, 2-way, 2-cycle latency
- L1 D-cache latency: 2 cycles
- L2 latency: 20 cycles
- Memory: `DDR3_1600_8x8`, 16 MiB
- Execution mode: SE
- Query heads: 4
- KV heads: 2
- Head dimension: 32
- Layers: 1
- Software threads: 2
- Repetitions: 10
- Warmup runs: 0
- KV format: Q4

## Deferred

- Core-count exploration is deferred until thread/core partitioning is generalized.
- Software-knob exploration is pending the final tutor/runtime decision.
- FP16 and Q8 KV formats are not active.
- Attention block size is not yet implemented.
- Alternative memory models require validation before activation.
- Memory latency and bandwidth knobs require explicit gem5 mappings before activation.
- Larger context lengths are deferred.

## Current implementation

### Experiment contracts

`experiment-contracts/` is the canonical configuration, design-space, schema,
compute-policy, and run-record layer.

### Hardware execution

`gem5/` contains the executable Q4 attention workload, configurable gem5 model,
experiment runner, and metric extraction pipeline.

The experiment YAML drives workload dimensions and hardware configuration rather
than serving only as metadata.

### Project scaffold

`src/` defines the stable software, hardware, and orchestration interfaces.

The hardware execution path exists under `gem5/`. Some `src/` adapters remain
intentional skeletons while integration work continues.

### Tutor side

The tutor runtime, software knobs, model adapter, evaluator, and software-side
metrics are still being finalized.

Reference material is used for evaluation only and is not automatically supplied
to the tutor as retrieval context.

## Compute policy

Use progressive validation: **Dev -> Integration -> Pilot -> Final**.

- Real API calls may be used during development/integration when needed.
- Larger compute should only be used after smaller stages validate correctly.
- Organizer burst resources are reserved for the frozen final campaign.
- Each run should preserve configuration, metrics, execution, cost, and provenance.

## Open questions

1. Final tutor runtime and model selection.
2. Final software knobs exposed to CHIA.
3. Exact tutor-to-attention proxy mapping.
4. Final answer-quality evaluation protocol and Pareto objectives.
5. Final organizer compute resources and parallelism limits.
