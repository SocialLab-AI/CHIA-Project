# Attention Experiment Contracts

This folder contains the contracts for the attention-kernel gem5 proxy path:

1. `attention-experiment.schema.json` — one concrete gem5 + attention run candidate, including actual emitted gem5 metrics.
2. `attention-design-space.schema.json` — the active hardware search space, baseline, fixed parameters, evaluation axes, and future knobs.
3. `baseline.attention.yaml` — the verified two-core Q4 KV-cache baseline in gem5.
4. `example.candidate.yaml` — a planned candidate from the active cache design space.
5. `design-space.yaml` — the active hardware search space document.

## Verified Q4 Baseline

- CPU: `RiscvO3CPU`
- Cores: `2`
- Frequency: `1 GHz`
- Issue width: `2`
- L1 I-cache: `16 KiB`, 2-way, 2-cycle latency
- L1 D-cache: `64 KiB`, 4-way, 2-cycle latency
- Shared L2: `1024 KiB`, 8-way, 20-cycle latency
- Memory: `DDR3_1600_8x8`
- Memory size: `16 MiB` (proxy workload physical address range)
- Mode: `SE` (gem5 syscall-emulation)
- Context length: `512`
- Query heads: `4`
- KV heads: `2`
- Head dimension: `32`
- Layers: `1`
- Software threads: `2`
- Repetitions: `10`
- Warmup runs: `0`
- KV format: `Q4`

## Hardware Search Space

### Active Hardware Knobs
- **CPU models**: `RiscvTimingSimpleCPU`, `RiscvO3CPU`
- **Frequency**: `1, 2, 3, 4 GHz`
- **Issue width**: `1, 2, 4`
  - *Compatibility constraint*: `RiscvTimingSimpleCPU` is constrained to issue width `1`. `RiscvO3CPU` supports `1, 2, 4`.
- **L1 D-cache capacity**: `16, 32, 64 KiB` (per core)
- **L1 D-cache associativity**: `2, 4, 8`
- **Shared L2 cache capacity**: `256, 512, 1024 KiB`
- **Shared L2 cache associativity**: `4, 8, 16`

### Fixed Parameters for Current Campaign
- **Cores**: `2` (core exploration deferred until multi-core partitioning is generalized)
- **KV format**: `Q4`
- **Software threads**: `2`
- **ISA**: `RISCV64`
- **L1 I-cache**: `16 KiB`, `2-way`, `2 cycles` latency per core
- **L1 D-cache latency**: `2 cycles`
- **L2 cache latency**: `20 cycles`
- **Memory model**: `DDR3_1600_8x8` (the validated gem5 DRAM configuration)
- **Memory size**: `16 MiB`
- **Simulation mode**: `SE`
- **Repetitions**: `10`
- **Warmup runs**: `0`

## Evaluation Axes
Context length is an **evaluation axis** (`128, 256, 512`), not an optimization knob. Compare candidates within the same workload condition.

## Metrics Interface
The emitted gem5 metrics contract records per-core cycles, IPC, CPI, cache miss rates, and DRAM bandwidth/latency. Hardware simulation latency is strictly separated from application latency.

## Deferred / Future Knobs
- Core counts (1, 4) deferred
- `FP16` and `Q8` KV formats
- `DDR4` memory model (requires experimental validation before activation)
- Attention block size
- Memory latency and bandwidth parameter mapping
- Context lengths beyond 512 (1024, 2048, 4096)
