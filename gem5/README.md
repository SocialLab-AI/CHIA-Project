# gem5 Q4 Attention Proxy

This directory contains the gem5 proxy workload for the Edge AI Tutor project. It models attention using a packed INT4 KV cache instead of running a complete LLM inside gem5.

## Files

- `attention_kv.c` — reviewed shared Q4 attention implementation with grouped-query mapping, generic head dispatch and FP32 validation
- `attention_kv_original_proxy.c` — frozen 4-query/2-KV/32-dimension entry profile from the repeated comparison
- `attention_kv_qwen_proxy.c` — frozen 14-query/2-KV/64-dimension Qwen-shaped entry profile from the repeated comparison
- `attention-riscv.py` — two-core RISC-V gem5 configuration
- `baseline-results.md` — verified baseline results

The two named proxy files include the same corrected shared implementation and
lock only the compared attention shape. The pre-correction kernel contained a
known KV mapping and head-dispatch defect, so it remains available through Git
history as evidence rather than as a selectable implementation. No final proxy
has been selected; see the [recorded comparison](../docs/experiments/proxy-comparison-results-20260918.md).

## Configuration

- 2 × `RiscvO3CPU`
- Issue width: 2
- Clock: 1 GHz
- L1 I-cache: 16 KiB, 2-way per core
- L1 D-cache: 64 KiB, 4-way per core
- Shared L2: 1 MiB, 8-way
- DDR3 memory: 16 MiB
- RISC-V SE mode
- Two software threads

## Compile

Run from this directory:

```bash
docker run --rm \
  -v "$PWD":/project/gem5 \
  -v "$HOME/gem5-src":/gem5-src \
  -w /project/gem5 \
  ghcr.io/gem5/devcontainer:v25-1 \
  riscv64-linux-gnu-gcc \
  -static -O2 -std=c11 -pthread \
  -o /gem5-src/attention_kv_q4 \
  attention_kv.c -lm
```

To reproduce either reviewed comparison profile, replace `attention_kv.c` in
the final command with `attention_kv_original_proxy.c` or
`attention_kv_qwen_proxy.c`. Set `CONTEXT` at compile time, for example:

```bash
riscv64-linux-gnu-gcc -static -O2 -std=c11 -pthread \
  -DCONTEXT=512 \
  -o /gem5-src/attention_kv_qwen \
  attention_kv_qwen_proxy.c -lm
```
