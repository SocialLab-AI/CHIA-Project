# AI Tutor Config Contract

## Purpose

Defines the **application-level** AI Tutor experiment: dataset/corpus, evaluation protocol, model, quantization, RAG controls, context limit, response limit, and application metrics.

This is the official Tutor-level contract. It intentionally does **not** contain gem5 cache/CPU knobs.

## Why hardware moved out

`l1_cache`, `l2_cache`, `cores`, and CPU-model settings describe the simulated attention proxy, not the Tutor application itself. Keeping them here would mix two abstraction levels.

## Proposed v0.2 changes from the original v0.1 record

Kept:
- `metadata.experiment_id`
- `metadata.description`
- `metadata.artifact_manifest`
- `workload.dataset_id`
- `workload.corpus_id`
- `workload.evaluation_protocol`
- `workload.num_questions`
- `workload.seed`
- model / quantization / retrieval / max-new-tokens / batch-size
- application status

Added:
- `software.max_context_tokens`
- `proxy_evaluation` reference to the attention-kernel layer

Moved out:
- gem5/simulated hardware knobs
- simulator-specific metrics

## Scientific reason

The Tutor evaluates application quality. The attention kernel evaluates a representative low-level compute path. CHIA can connect the two, but the contracts should not pretend they are the same experiment.
