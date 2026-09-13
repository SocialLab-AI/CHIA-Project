# gem5 Q4 Attention Proxy

This directory contains the gem5 proxy workload for the Edge AI Tutor project. It models attention using a packed INT4 KV cache instead of running a complete LLM inside gem5.

## Files

- `attention_kv.c` — Q4 KV-cache attention kernel with FP32 validation
- `attention-riscv.py` — two-core RISC-V gem5 configuration
- `baseline-results.md` — verified baseline results

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
