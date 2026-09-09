# Current Project State

## Current thesis

Build an offline AI Tutor experiment where CHIA orchestrates software/hardware exploration and uses an attention kernel with a quantized KV cache as the gem5 proxy for LLM inference behavior.

## Current baseline

| Parameter | Value |
| --- | --- |
| CPU | `RiscvTimingSimpleCPU` |
| Cores | 1 |
| Frequency | 1 GHz |
| L1 I-cache | 16 KiB, 2-way |
| L1 D-cache | 16 KiB, 2-way |
| L2 cache | 256 KiB, 8-way |
| Memory | `DDR3_1600_8x8` |
| Memory size | 16 MiB |
| Execution mode | SE |
| Context length | 512 |
| Query heads | 4 |
| KV heads | 2 |
| Head dimension | 32 |
| Layers | 1 |
| Threads | 1 |
| Repetitions | 4 |
| Warmup | 0 |
| KV format | FP32 baseline |

## Active initial search space

- L1 D-cache: 16 / 32 / 64 KiB
- L2 cache: 256 / 512 / 1024 KiB
- Context length 128 / 256 / 512 is an evaluation axis rather than a knob to minimize.

## Fixed or deferred

- `RiscvO3CPU`: future until validated.
- Frequency sweep 1–4 GHz: future.
- Multiple cores/threads: future until a parallel workload exists.
- Attention block size: future until implemented.
- FP16/Q8/Q4: planned; activate only after implementation and validation.
- Memory latency/bandwidth: future until correctly mapped to gem5 memory parameters.

## Compute policy

Use progressive validation: **Dev -> Integration -> Pilot -> Final**.

- Real Gemini API calls are allowed during development/integration when needed.
- Use stronger development compute if the local/Contabo server is insufficient.
- Organizer burst compute is reserved for the frozen final campaign.
- Nothing scales until a smaller validated stage works.

## Schema architecture

- **AI Tutor Config** — application-level dataset/corpus/model/RAG contract.
- **Attention Experiments** — concrete attention/gem5 experiment plus design space.
- **Compute Policy** — real execution, backend, and parallelism guardrails.
- **Run Record** — measured metrics, cost, execution, and provenance evidence.

## Open questions

1. Exact Tutor-to-attention mapping after target model/runtime selection.
2. When Q8/Q4 become verified.
3. Whether cache associativity enters the first CHIA search.
4. Final organizer burst resources and safe parallelism.
5. Final evaluation metrics and Pareto objectives.
