# Attention Experiment Contracts

This folder contains two related contracts:

1. `attention-experiment.schema.json` — one concrete gem5 + attention run candidate. Hardware configuration delegates to canonical `chia-experiment.schema.json#/$defs/hardware_config`.
2. `attention-design-space.schema.json` — the values CHIA is allowed to explore, the baseline, fixed controls, evaluation axes, and future knobs. Hardware active knob candidates delegate to `chia-experiment.schema.json#/$defs/hardware_active_knob_candidates`.

Workload controls specific to the attention kernel (e.g., `context_tokens`, `query_heads`, `kv_heads`, `head_dimension`, `layers`, `measurement`) are retained here as proxy workload definitions distinct from the general hardware platform.

## Canonical Hardware Source of Truth

The hardware configuration and search space are defined authoritatively in:
`configs/schemas/chia-experiment.schema.json`

### Active Hardware Knobs (8 Knobs)
- **CPU models**: `RiscvTimingSimpleCPU`, `RiscvO3CPU`
- **Core choices**: `1, 2, 4`
- **Frequency choices**: `1, 2, 3, 4 GHz`
- **Issue width choices**: `1, 2, 4`
  - *Compatibility constraint*: Enforced canonically in `hardware_config`: `RiscvTimingSimpleCPU` requires `issue_width == 1`. `RiscvO3CPU` supports `1, 2, 4`.
- **L1 D-cache capacity**: `16, 32, 64 KiB` (per core)
- **L1 D-cache associativity**: `2, 4, 8`
- **L2 cache capacity**: `256, 512, 1024 KiB` (total shared)
- **L2 cache associativity**: `4, 8, 16`

### Fixed Hardware Parameters (10 Parameters)
- **ISA**: `RISCV64` (canonical target ISA)
- **L1 I-cache**: `16 KiB`, `2-way` associativity, `2 cycles` latency (fixed per core)
- **L1 D-cache latency**: `2 cycles` (fixed)
- **L2 cache latency**: `20 cycles` (fixed)
- **Memory model**: `DDR3_1600_8x8` (the only validated gem5 memory model)
- **Memory size**: `16 MiB` (physical address range assigned to the proxy workload)
- **Simulation mode**: `SE` (gem5 syscall-emulation mode)
- **Software threads**: `2` (fixed baseline; relationship with varying core count is a future clarification)

## Software Formats Status (Attention Kernel)
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
