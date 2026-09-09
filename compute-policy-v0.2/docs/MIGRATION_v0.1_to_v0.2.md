# Migration: v0.1 AI-Tutor Schema -> v0.2 Attention-Kernel Contracts

## Why migrate

The original v0.1 schema was designed around a full AI Tutor/RAG workload. The project direction now uses an **attention kernel as the controlled proxy workload** for hardware/software co-design. Keeping RAG-only fields in the primary experiment contract would make the schema describe a system we are no longer simulating directly.

## Keep

- `schema_version`
- experiment identifiers/descriptions
- strict field names, types, units, bounds
- deterministic validation before execution
- hardware knobs such as L1/L2/cores/issue width, subject to gem5 mapping verification
- reproducibility metadata/seeds
- consistent result records for Pareto/baseline analysis

## Replace or remove from the primary attention experiment

| v0.1 field | v0.2 action | Reason |
|---|---|---|
| `workload.dataset` / OpenStax fields | Remove from kernel experiment | Kernel simulation is not full QA evaluation. |
| `software.model` | Remove | Not a full-model inference experiment. |
| `software.quantization` | Replace with workload/kernel `dtype` if relevant | Precision is now an attention-kernel representation concern. |
| `software.retrieval_top_k` | Remove | RAG-specific. |
| `software.max_new_tokens` | Remove | Generation-specific. |
| `metrics.answer_quality` | Remove from kernel run record | Kernel correctness replaces tutoring-answer quality at this layer. |
| `metrics.throughput_qps` | Reconsider | Use only if a well-defined kernel throughput metric is implemented. |
| `metrics.energy_joules` | Defer until model is validated | Do not publish modeled energy without a trustworthy mapping. |

## Add

### Attention workload dimensions

- `sequence_length`
- `head_dimension`
- `num_heads`
- `batch_size`
- `dtype`
- `causal`
- `seed`

### Kernel/software controls

- `kernel_variant`
- optional `tile_q`, `tile_k`, `tile_v`
- `num_threads`
- compiler flags where controlled

### Correctness

At minimum:

- `correctness.passed`
- `max_abs_error`
- `max_rel_error`

Correctness must be deterministic and checked before treating a performance result as valid.

### Execution governance

Do **not** place real host/backend controls inside `hardware.*`. Introduce a separate compute-policy contract.

### Provenance and usage

Record:

- exact Git commit;
- CHIA, gem5, and kernel versions;
- seed;
- Gemini prompt/model version;
- actual backend/tier;
- Gemini calls/tokens/estimated cost.

## Recommended split

Instead of one mutable YAML that starts as input and ends as output, use:

```text
experiment.yaml      immutable scientific candidate
compute-policy.yaml  team governance/admission policy
run-record.yaml      observed output/provenance/usage
```

This makes accidental mutation harder and makes experiment/result joins explicit through `experiment_id` and `config_digest`.

## Compatibility strategy

Do not silently reinterpret old v0.1 files. Keep `schema_version: "0.1"` for historical records and create `0.2` as a new contract. If an automatic migration script is later added, it should reject RAG fields that have no meaningful attention-kernel equivalent rather than inventing values.
