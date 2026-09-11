# Run Record Contract

## Purpose

Stores **evidence from what actually happened**, not what we intended to run.

This contract delegates canonically to `configs/schemas/chia-experiment.schema.json#/$defs/run_record`.

## Metrics Architecture

Metrics are organized under a unified container (`metrics:`) strictly separating application-level metrics from gem5 hardware metrics. A completed run may contain application metrics, hardware metrics, or both:

- **Application metrics** (`metrics.application`):
  - `answer_quality` (output objective to maximize)
  - `latency_ms` (real Tutor application end-to-end response time to minimize)
  - `memory_mb`
  - `throughput_qps`

- **Hardware metrics** (`metrics.hardware`):
  - `execution_cycles`
  - `instructions`
  - `cpi`
  - `ipc`
  - `sim_ticks`
  - `sim_seconds`
  - `l1i_miss_rate`
  - `l1d_miss_rate`
  - `l2_miss_rate`
  - `checksum`
  - `passed`

Application latency (`latency_ms`) is strictly isolated from simulated time (`sim_seconds`). Neither `answer_quality` nor `latency_ms` is a knob.

## Execution, Usage, and Provenance

Also stores canonical execution records:
- `execution`: tier (`dev`, `integration`, `pilot`, `final`), backend (`local`, `contabo`, `development_cloud`, `organizer_burst`), `worker_id`, timing, `attempt`, `host_seconds`.
- `usage`: Gemini API telemetry (`model`, `calls`, `input_tokens`, `output_tokens`, `estimated_cost_usd`).
- `provenance`: Git commit, CHIA version, gem5 version, kernel version, compiler, policy version, seed.
- `status`: execution status (`state`, `failure_reason`).
