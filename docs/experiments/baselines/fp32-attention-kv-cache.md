# FP32 Attention KV Cache gem5 Run Report

**Proxy candidate:** Single-token FP32 attention with a KV cache  
**ISA:** RISC-V  
**Status:** Successfully executed in gem5

> Evidence record: preserve the measured values and original execution details. If the implementation changes materially, create a new run record instead of rewriting this one.

## Exact commands used

### Persistent gem5 container

```bash
docker run -d \
  --name gem5-dev \
  --restart unless-stopped \
  -v /home/yehya/gem5-src:/gem5-src \
  ghcr.io/gem5/devcontainer:v25-1 \
  sleep infinity

docker exec -it -w /gem5-src gem5-dev bash
```

### Cross compilation

```bash
riscv64-linux-gnu-gcc -static -O2 -std=c11 \
  -o attention_kv_fp32 attention_kv.c -lm
```

The output binary was reported as:

- ELF 64-bit LSB executable
- UCB RISC-V
- RVC
- Double-float ABI
- Statically linked
- GNU/Linux 4.15.0

### gem5 simulation

Configuration file:

```text
/gem5-src/attention-riscv-cached.py
```

Simulation command:

```bash
gem5 \
  --outdir=/gem5-src/run-attention-fp32-cached \
  /gem5-src/attention-riscv-cached.py
```

Metrics command:

```bash
grep -E \
  '^(simInsts|simTicks|simSeconds|hostSeconds|system\.cpu\.(cpi|ipc)|system\.(icache|dcache|l2cache)\.overallMissRate::total)' \
  /gem5-src/run-attention-fp32-cached/stats.txt
```

## Attention KV cache dimensions

| Parameter | Value |
| --- | --- |
| Context length | 512 tokens |
| Query heads | 4 |
| KV heads | 2 |
| Head dimension | 32 |
| Attention layers | 1 |
| Repetitions | 4 |
| Data format | FP32 |
| Execution | Single-threaded |

The workload uses grouped-query attention. Four query heads share two KV heads.

Approximate FP32 KV-cache size:

```text
2 x 512 x 2 x 32 x 4 bytes = 256 KiB
```

The factor of two represents the key and value caches.

## gem5 CPU and cache configuration

| Component | Configuration |
| --- | --- |
| CPU | `RiscvTimingSimpleCPU` |
| CPU behavior | In-order, single-issue |
| CPU cores | 1 |
| Threads | 1 |
| Clock | 1 GHz |
| L1 instruction cache | 16 KiB, 2-way |
| L1 data cache | 16 KiB, 2-way |
| L2 cache | 256 KiB, 8-way |
| Main memory | `DDR3_1600_8x8` |
| Memory range | 16 MiB |
| Execution mode | Syscall Emulation |
| Vector instructions | Not used |

## Program output

```text
ATTENTION_FP32_RESULT
context=512
query_heads=4
kv_heads=2
head_dimension=32
repetitions=4
checksum=55.695413424
status=PASS
```

The successful status and finite checksum confirm that the attention workload executed correctly.

## Simulation results

| Metric | Result |
| --- | ---: |
| Checksum | 55.695413424 |
| simInsts | 5,083,326 |
| simTicks | 22,083,333,000 |
| Simulated cycles | 22,083,333 |
| simSeconds | 0.022083 |
| CPI | 4.344248 |
| IPC | 0.230189 |
| L1 instruction-cache miss rate | 0.000062 |
| L1 data-cache miss rate | 0.036725 |
| L2-cache miss rate | 0.188856 |
| gem5 host runtime | 11.15 seconds |

At 1 GHz, one simulated CPU cycle corresponds to 1,000 gem5 ticks:

```text
22,083,333,000 ticks / 1,000 = 22,083,333 cycles
```

## Important findings

- The instruction-cache miss rate was almost zero, showing that the program instructions fit comfortably in the instruction cache.
- The L1 data-cache miss rate was approximately 3.67%, showing that the attention data created measurable cache activity.
- The L2 miss rate was approximately 18.89%, indicating that some requests could not be served by the 256 KiB L2 cache and needed main-memory access.
- The FP32 KV cache is approximately the same size as the 256 KiB L2 cache. Additional program data and cache effects prevent the entire working set from remaining in L2.

## Issues and limitations

1. **Docker and gem5 version mismatch.** The Docker image is tagged `v25-1`, but the gem5 executable reports version `24.1.0.1`.
2. **DRAM capacity warning.** gem5 reported that the DDR3 device capacity is 8 GiB while the assigned address range is 16 MiB. The simulation completed successfully.
3. **Syscall warnings.** gem5 ignored `set_robust_list` and `mprotect` in SE mode. These warnings did not affect the final result.
4. **FP32 only.** Q8 and Q4 KV-cache quantization have not been implemented or tested yet.
5. **No no-cache comparison.** Only the cached configuration was tested.
6. **No Region of Interest.** Statistics include program initialization, attention execution, mathematical-library work, and output operations.
7. **Synthetic dimensions.** The dimensions are suitable for an initial test but have not yet been derived from the final target LLM.
8. **Single core and scalar execution.** The workload uses one core and does not exercise the available RISC-V Vector extension.

## Conclusion

The FP32 attention KV-cache proxy compiled successfully as a static RISC-V binary and executed correctly in gem5 SE mode.

The workload completed with 5,083,326 instructions, approximately 22.08 million simulated cycles, and an 11.15-second host runtime. Its 256 KiB FP32 KV cache created measurable L1, L2, and main-memory activity.

This confirms that the attention workload is functional and can be used as the baseline for later KV-cache quantization and hardware/software comparisons.
