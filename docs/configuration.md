# Configuration

`experiment-contracts/` is the configuration source of truth. The current checkout uses domain JSON schemas and shared definitions, with YAML input files. A proposed single YAML master schema is not present in this checkout; do not document it as implemented.

## Files to edit

| Purpose | Current file |
|---|---|
| Tutor baseline | [example.ai-tutor.yaml](../experiment-contracts/ai-tutor-config/example.ai-tutor.yaml) |
| Pending software search | [Tutor design space](../experiment-contracts/ai-tutor-config/design-space.yaml) |
| Hardware proxy baseline | [baseline.attention.yaml](../experiment-contracts/attention-experiments/baseline.attention.yaml) |
| Active hardware search | [Attention design space](../experiment-contracts/attention-experiments/design-space.yaml) |
| Candidate example | [example.candidate.yaml](../experiment-contracts/attention-experiments/example.candidate.yaml) |
| Compute policy | [compute-policy.yaml](../experiment-contracts/compute-policy/compute-policy.yaml) |
| Execution evidence example | [example.completed.yaml](../experiment-contracts/run-records/example.completed.yaml) |
| Common schema definitions | [shared.schema.json](../experiment-contracts/schemas/shared.schema.json) |

Each domain schema is located beside its example. The [validator](../scripts/validate_configs.py) registers them locally and validates the maintained inputs. YAML contains selected values; schemas specify structure and legal values; design spaces distinguish active, fixed and deferred settings.

## Editing rules

1. Edit the appropriate canonical YAML input. Preserve historical measured baselines; create a separate candidate for a new experiment.
2. For a new field, reconcile schema rules, design space, adapter capability, [mapping documentation](knob-mapping.md), and [manifest](knob-mapping.manifest.json).
3. Run validation before execution. Keep software runtime readiness false while artifacts or adapters are unresolved.
4. Do not invent software search ranges from baseline values. Character-based chunk settings must not silently become token counts.

The tutor baseline uses four native threads; the attention proxy uses two simulated workload threads and fixes two cores. These values are independent. Q4_K_M model weights do not select the proxy KV-cache format.

## Metric naming at the integration boundary

The current extractor emits `simulated_seconds`, `cycles_per_core`, `ipc_per_core` and DRAM measurements. The separate run-record schema still uses some older names, including `sim_seconds`. This requires an explicit mapping or later contract alignment; do not silently treat the two output shapes as interchangeable. This documentation cleanup does not change their schemas.

## Previous layouts

`configs/`, `config-schema/` and `compute-policy-v0.2/` are superseded. Use the files above and the common validator. Detailed migration history remains in Git; old folder diagrams are not current setup instructions.
