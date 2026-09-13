# Run Record Contract

## Purpose

Stores **evidence from what actually happened**, not what we intended to run.

This contract defines the schema and format for run records under `run-record.schema.json`.

## Verified Metrics Currently Included

- execution cycles
- instructions
- CPI
- IPC
- `sim_ticks`
- `sim_seconds`
- host runtime / `host_seconds`
- L1 instruction-cache miss rate (`l1i_miss_rate`)
- L1 data-cache miss rate (`l1d_miss_rate`)
- L2 miss rate (`l2_miss_rate`)
- checksum
- PASS/FAIL (`passed`)

Also stores:
- execution tier/backend (`execution`)
- config digest (`experiment.config_digest`)
- Gemini metering (`usage.gemini`)
- tool/code provenance (`provenance`)
- failure/retry state (`status`)

## Application vs Hardware Separation

Application metrics (such as `answer_quality` and end-to-end `latency_ms`) are strictly isolated from simulated hardware metrics (`sim_seconds`, `sim_ticks`, `execution_cycles`). Application latency is real wall-clock latency, not simulated gem5 time.

## Planned Metrics Intentionally Omitted from the Required Record

These should be added only after implementation/validation:
- maximum absolute error
- mean squared error
- NaN/Infinity detection
- memory-bandwidth utilization
- bytes transferred
- average memory-access latency

This avoids confusing "not implemented" with "measured but missing".
