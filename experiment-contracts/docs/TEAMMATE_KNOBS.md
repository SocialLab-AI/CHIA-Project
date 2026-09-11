# Team-Supplied Attention/gem5 Knobs

This file records the current teammate-provided implementation direction and hardware contracts.

## Baseline Configuration

- `RiscvO3CPU` baseline
- Cores: `2`
- Frequency: `1 GHz`
- Issue width: `2`
- L1I cache: `16 KiB`, `2-way`, `2 cycles` latency
- L1D cache: `64 KiB`, `4-way`, `2 cycles` latency
- L2 cache: `1024 KiB`, `8-way`, `20 cycles` latency
- Memory type: `DDR3_1600_8x8`
- Memory size: `16 MiB` proxy physical address space
- Simulation mode: `SE` (syscall-emulation)
- Context tokens: `512` baseline (`128, 256, 512` evaluation axis)
- Query heads: `4`
- KV heads: `2`
- Head dimension: `32`
- Layers: `1`
- Threads: `1`
- Repetitions: `4`
- Warmup runs: `0`
- KV format: `FP32` baseline

## Active Knobs (Search Space)

- `cpu_model`: `[RiscvTimingSimpleCPU, RiscvO3CPU]`
- `cores`: `[1, 2, 4]`
- `frequency_ghz`: `[1, 2, 3, 4]`
- `issue_width`: `[1, 2, 4]` (compatibility constraint: `RiscvTimingSimpleCPU` restricted to `1`; `RiscvO3CPU` supports `1, 2, 4`)
- `l1d_cache_kib`: `[16, 32, 64]`
- `l1d_associativity`: `[2, 4, 8]`
- `l2_cache_kib`: `[256, 512, 1024]`
- `l2_associativity`: `[4, 8, 16]`

## Fixed Parameters

- `l1i_cache_kib`: `16`
- `l1i_associativity`: `2`
- `l1i_latency_cycles`: `2`
- `l1d_latency_cycles`: `2`
- `l2_latency_cycles`: `20`
- `memory_type`: `DDR3_1600_8x8`
- `memory_size_mib`: `16`
- `simulation_mode`: `SE`

## Software Formats Status

- **Currently Validated by the Proxy**: `FP32`, `Q4`
- **Planned / Not Yet Validated**: `FP16`, `Q8`

## Memory Model Policy

- **Validated**: `DDR3_1600_8x8`
- **Excluded**: `DDR4` is not yet validated and remains strictly outside the active schema.

## Future / Gated Knobs

- `FP16` and `Q8` KV formats
- `DDR4` memory model
- Attention block size
- Memory latency mapping
- Bandwidth mapping
- Multi-threaded parallel kernel
- Extended context lengths (1024, 2048, 4096)
