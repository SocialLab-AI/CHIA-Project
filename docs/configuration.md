# Configuration

`experiment-contracts/` is the configuration source of truth. The master YAML schema defines baseline, design-space, candidate and completed-record shapes; YAML files hold reviewed values.

## Files to edit

| Purpose | Current file |
|---|---|
| Tutor baseline | [tutor.yaml](../experiment-contracts/baselines/tutor.yaml) |
| Software design space | [software.yaml](../experiment-contracts/design-spaces/software.yaml) |
| Hardware proxy baseline | [attention.yaml](../experiment-contracts/baselines/attention.yaml) |
| Hardware design space | [hardware.yaml](../experiment-contracts/design-spaces/hardware.yaml) |
| Candidate example | [attention-candidate.yaml](../experiment-contracts/examples/attention-candidate.yaml) |
| Compute policy | [compute-policy.yaml](../experiment-contracts/policies/compute-policy.yaml) |
| Execution evidence example | [completed-run.yaml](../experiment-contracts/examples/completed-run.yaml) |
| Master schema | [chia-experiment.schema.yaml](../experiment-contracts/schemas/chia-experiment.schema.yaml) |

The [validator](../scripts/validate_configs.py) checks structure, semantic policy, rejection cases and agreement with the knob manifest. The smaller executable software candidate space used by the loop is [software-design-space.yaml](../experiment-contracts/testing/software-design-space.yaml).

## Editing rules

1. Edit the appropriate canonical YAML input. Preserve historical measured baselines; create a separate candidate for a new experiment.
2. For a new field, reconcile schema rules, design space, adapter capability, [mapping documentation](knob-mapping.md), and [manifest](knob-mapping.manifest.json).
3. Run validation before execution. Runtime readiness requires the exact GGUF path/hash and matching llama.cpp context/slot configuration.
4. Do not invent search ranges from baseline values. Fixed knobs remain outside Gemini's proposal shape.

The Tutor baseline uses four native threads; the attention proxy uses two simulated workload threads and fixes two cores. These values are independent. Q5_K_M model weights do not select the proxy KV-cache format.

The final run record keeps software metrics, hardware metrics and correctness evidence in separate named objects. Native Tutor latency must not be interpreted as gem5 simulated time, and attention-proxy results must not be described as full-model simulation.
