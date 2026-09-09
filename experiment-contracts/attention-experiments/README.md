# Attention Experiment Contracts

This folder contains two related contracts:

1. `attention-experiment.schema.json` — one concrete gem5 + attention run candidate.
2. `attention-design-space.schema.json` — the values CHIA is allowed to explore, the baseline, fixed controls, evaluation axes, and future knobs.

## Team-grounded baseline

- CPU: `RiscvTimingSimpleCPU`
- Cores: `1`
- Frequency: `1 GHz`
- L1 I-cache: `16 KiB`, 2-way, 2-cycle
- L1 D-cache: `16 KiB`, 2-way, 2-cycle
- L2: `256 KiB`, 8-way, 20-cycle
- Memory: `DDR3_1600_8x8`
- Memory size: `16 MiB`
- Mode: `SE`
- Context: `512`
- Query heads: `4`
- KV heads: `2`
- Head dimension: `32`
- Layers: `1`
- Threads: `1`
- Repetitions: `4`
- Warmup: `0`
- KV format: `FP32`

## Initial active CHIA search

Keep the first search intentionally small and causal:

- L1 D-cache: `16, 32, 64 KiB`
- L2: `256, 512, 1024 KiB`
- KV format: currently `FP32` only until additional formats are verified

Context length is an **evaluation axis** (`128, 256, 512`), not a "choose the smallest to win" optimization knob.

## Future / not yet active

- `RiscvO3CPU`
- frequency sweep `1-4 GHz`
- L1/L2 associativity sweeps
- FP16 / Q8 / Q4 until implementation is verified
- attention block size
- memory latency
- memory bandwidth
- multithreading
- context beyond 512 until runtime testing
