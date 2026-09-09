# Team-Supplied Attention/gem5 Knobs

This file records the current teammate-provided implementation direction.

## Active or baseline now

- `RiscvTimingSimpleCPU` baseline
- 1 core
- 1 GHz
- L1I: 16 KiB, 2-way
- L1D: 16 KiB baseline; 16/32/64 KiB candidates
- L2: 256 KiB baseline; 256/512/1024 KiB candidates
- L1 latency: 2 cycles
- L2 latency: 20 cycles
- memory: DDR3_1600_8x8
- memory size: 16 MiB constraint
- context: 128/256/512 evaluation axis; 512 baseline
- query heads: 4
- KV heads: 2
- head dimension: 32
- layers: 1
- threads: 1
- repetitions: 4
- warmup: 0
- KV format: FP32 baseline

## Future / gated

- RiscvO3CPU
- frequency sweep 1-4 GHz
- cache associativity sweeps
- FP16/Q8/Q4 if/when verified
- attention block size
- memory latency mapping
- bandwidth mapping
- more threads
- context to 4096 after runtime testing
