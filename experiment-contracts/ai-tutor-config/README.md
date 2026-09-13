# AI Tutor Config Contract

## Purpose

Defines the **application-level** AI Tutor experiment: dataset/corpus, evaluation protocol, model, quantization, RAG controls, character-level chunking, and application metrics.

This folder contains:
1. `ai-tutor.schema.json` — application-level experiment schema.
2. `example.ai-tutor.yaml` — concrete software baseline candidate.
3. `design-space.yaml` — software design space document (software search recorded as pending).
4. `ai-tutor-design-space.schema.json` — schema validating the software design space.

## Software Baseline Specification

The baseline reflects the user-supplied configuration:
- **Model**: `Llama 3.2 1B Instruct`
- **Model-weight quantization**: `Q4_K_M`
- **Backend**: `llama.cpp / CPU`
- **CPU threads**: `4` (native tutor CPU threads are independent of the gem5 proxy's 2 threads)
- **Batch size**: `1` (runtime mapping pending; not automatically mapped to llama.cpp `n_batch`)
- **Sampling temperature**: `0.0`
- **Maximum output tokens**: `384`
- **Embedding model**: `MiniLM-L6-dot-v1` (exact repository identifier unresolved)
- **Embedding dimension**: `384`
- **Retrieval method**: `Semantic similarity` (specific distance function unresolved)
- **Top-k**: `2`
- **Chunk size**: `1500` characters (measured in **CHARACTERS**, not tokens)
- **Chunk overlap**: `200` characters (measured in **CHARACTERS**, not tokens; must be `< chunk_size`)

## Software Search Space Status

This is a fixed baseline for initial co-design comparison. Software search is recorded as pending; alternative values and ranges are deferred until runtime adapters and artifact resolution are completed.

## Evaluation and Reference Isolation Guardrail

OpenStax reference answers (`data/references/openstax.json`) are used **strictly for evaluation**:
- `reference_source: "openstax"`
- `reference_visible_to_model: false`

Reference answers are NEVER visible to the model or ingested into the RAG corpus.

## Metric Separation

Application metrics (`answer_quality` and end-to-end `latency_ms`) are strictly separated from simulated gem5 hardware metrics (`sim_seconds`, `sim_ticks`, `execution_cycles`):
- `answer_quality` is an application output to maximize.
- `latency_ms` is real wall-clock application latency to minimize.
Neither is a search knob.
