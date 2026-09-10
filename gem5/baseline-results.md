# Q4 Attention Proxy — gem5 Baseline

## Workload

- Attention kernel with packed INT4 KV cache
- Context length: 512 tokens
- Query heads: 4
- KV heads: 2
- Head dimension: 32
- Software threads: 2
- Repetitions: 10
- FP32 query, softmax, scaling, and accumulation

## Hardware configuration

- CPU: 2 × RiscvO3CPU
- Issue width: 2
- Clock: 1 GHz
- L1 I-cache: 16 KiB, 2-way per core
- L1 D-cache: 64 KiB, 4-way per core
- Shared L2: 1 MiB, 8-way
- Memory: DDR3_1600_8x8, 16 MiB
- ISA/mode: RISC-V, SE mode

## Correctness

- FP32 checksum: 55.695413424
- Q4 checksum: 55.207520567
- Maximum absolute error: 0.007946730
- Mean squared error: 0.000006495
- Status: PASS

## Performance

- Simulated ticks: 16,120,761,000
- Simulated time: 0.016121 seconds
- Instructions: 31,245,140
- CPU 0 IPC: 1.112463
- CPU 1 IPC: 1.759869
- CPU 0 D-cache miss rate: 1.6808%
- CPU 1 D-cache miss rate: 1.9031%
- L2 miss rate: 69.9803%
- Host runtime: 181.29 seconds

## Limitations

The FP32 reference calculation is included in the measured program, so the statistics are not exclusively Q4 execution. The workload is a representative attention proxy rather than full LLM inference. RVV is available in gem5 but is not used.
