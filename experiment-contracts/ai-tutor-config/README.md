# AI Tutor Config Contract

## Purpose

Defines the **application-level** AI Tutor experiment: dataset/corpus, evaluation protocol, model, quantization, RAG controls, context limit, response limit, and application metrics.

This schema is a thin compatibility contract that references canonical definitions from `configs/schemas/chia-experiment.schema.json`:
- `software` delegates to `chia-experiment.schema.json#/$defs/software_config`
- `metadata` delegates to `chia-experiment.schema.json#/$defs/metadata`
- `metrics` delegates to `chia-experiment.schema.json#/$defs/metrics`
- `status` delegates to `chia-experiment.schema.json#/$defs/status`

It preserves the application-level `proxy_evaluation` bridge linking the Tutor experiment to the low-level attention proxy kernel.

## Current Software Architecture Status

The AI Tutor architecture is confirmed as:
- **Parameter scale**: 1B (`parameter_count = "1B"`)
- **Runtime**: Ollama (`runtime = "ollama"`)
- **Model**: Quantized (`quantization` is an active CHIA knob)
- **RAG**: Enabled (`rag.enabled = true`)

The 4 official active software knobs are:
1. `temperature`
2. `chunk_overlap`
3. `similarity_metric`
4. `quantization`

Concrete candidate values and baseline definitions remain pending team definition (`runtime_ready: false`).

## Metric Isolation

Application metrics (`answer_quality` and `latency_ms`) are strictly separated from low-level gem5 simulated hardware metrics (`sim_seconds`, `execution_cycles`, `ipc`).
- `answer_quality` is an optimization output to maximize.
- `latency_ms` is an end-to-end application response time to minimize.
Neither is a search knob.
