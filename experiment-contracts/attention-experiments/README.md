# Attention Experiment Contracts

This folder contains two related contracts:

1. `attention-experiment.schema.json` — one concrete gem5 + attention run candidate.
2. `attention-design-space.schema.json` — the values CHIA is allowed to explore, the baseline, fixed controls, evaluation axes, and future knobs.

## Team-grounded baseline

- CPU: `RiscvO3CPU`
- Cores: `2`
- Frequency: `1 GHz`
- Issue width: `2`
- L1 I-cache: `16 KiB`, 2-way, 2-cycle latency
- L1 D-cache: `64 KiB`, 4-way, 2-cycle latency
- L2: `1024 KiB`, 8-way, 20-cycle latency
- Memory: `DDR3_1600_8x8`
- Memory size: `16 MiB` (proxy-workload physical address range)
- Mode: `SE` (gem5 syscall-emulation)
- Context: `512`
- Query heads: `4`
- KV heads: `2`
- Head dimension: `32`
- Layers: `1`
- Threads: `1`
- Repetitions: `4`
- Warmup: `0`
- KV format: `FP32`

## Hardware Contract Specification

### Variable Knobs (Search Space)
- **CPU models**: `RiscvTimingSimpleCPU`, `RiscvO3CPU`
- **Core choices**: `1, 2, 4`
- **Frequency choices**: `1, 2, 3, 4 GHz`
- **Issue width choices**: `1, 2, 4`
  - *Compatibility constraint*: `RiscvTimingSimpleCPU` supports only issue width `1`. `RiscvO3CPU` supports `1, 2, 4`.
- **L1 D-cache capacity**: `16, 32, 64 KiB` (per core)
- **L1 D-cache associativity**: `2, 4, 8`
- **L2 cache capacity**: `256, 512, 1024 KiB` (total shared)
- **L2 cache associativity**: `4, 8, 16`

### Fixed Hardware Parameters
- **L1 I-cache**: `16 KiB`, `2-way` associativity, `2 cycles` latency (fixed per core)
- **L1 D-cache latency**: `2 cycles` (fixed)
- **L2 cache latency**: `20 cycles` (fixed)
- **Memory model**: `DDR3_1600_8x8` (the only validated gem5 memory model)
- **Memory size**: `16 MiB` (physical address range assigned to the proxy workload)
- **Simulation mode**: `SE` (gem5 syscall-emulation mode)

### Memory Model Policy
- **DDR3_1600_8x8**: currently validated memory model.
- **DDR4**: excluded until tested (planned / not yet validated / out of current schema).

## Software Formats Status
- **Currently validated by the proxy**: `FP32`, `Q4`
- **Planned / not yet validated**: `FP16`, `Q8`

## Evaluation Axes
Context length is an **evaluation axis** (`128, 256, 512`), not an optimization knob.

## Future / Not Yet Active
- `FP16`, `Q8` KV formats (until implementation is verified)
- `DDR4` memory model (until experimentally established and validated)
- Attention block size
- Memory latency mapping to gem5 DRAM parameters
- Bandwidth mapping
- Parallel kernel multithreading
- Context lengths beyond 512 (1024, 2048, 4096) after runtime testing
