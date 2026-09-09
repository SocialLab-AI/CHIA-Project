# Run Record Contract

## Purpose

Stores **evidence from what actually happened**, not what we intended to run.

Verified kernel/gem5 metrics currently included:
- execution cycles
- instructions
- CPI
- IPC
- `simTicks`
- `simSeconds`
- host runtime / `hostSeconds`
- L1 instruction-cache miss rate
- L1 data-cache miss rate
- L2 miss rate
- checksum
- PASS/FAIL

Also stores:
- execution tier/backend
- config digest
- Gemini metering
- tool/code provenance
- failure/retry state

## Planned metrics intentionally omitted from the required record

These should be added only after implementation/validation:
- maximum absolute error
- mean squared error
- NaN/Infinity detection
- memory-bandwidth utilization
- bytes transferred
- average memory-access latency

This avoids confusing "not implemented" with "measured but missing".
