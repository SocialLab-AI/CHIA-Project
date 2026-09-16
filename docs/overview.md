# Project overview

The project explores hardware/software co-design for an offline AI Tutor. The intended CHIA loop proposes candidate settings, validates them, executes workloads, and compares measured outcomes. The complete automated loop is still under development.

The native Tutor runs Qwen2.5 0.5B Instruct with Q5_K_M weights through a loopback llama.cpp server on Adam. Three attributed OpenStax questions provide deterministic required-concept quality evidence. An attention kernel with packed Q4 KV cache remains the gem5 proxy; it does not execute the full Tutor model.

## Current status

| Area | Observed repository state |
|---|---|
| Contracts | Domain JSON schemas, shared definitions, YAML examples and design spaces, and a common validator exist. |
| Hardware path | Executable workload, gem5 configuration, runner, and metric extraction exist under `gem5/`. The repository records a Q4 baseline run. |
| Native tutor | Baseline is specified; runtime readiness is false. Model artifacts and adapter implementation remain unresolved. |
| Integration | `src/` provides interfaces; the hardware/tutor runners and CHIA entrypoint still contain unimplemented boundaries. |
| Search | Hardware knobs plus reviewed temperature/output limits are active; model identity and proxy Q4 remain fixed. |

See the [configuration guide](configuration.md) for authoritative inputs and the [evidence index](experiments/README.md) for measured reports. Documentation inspection and schema tests are not new simulator execution evidence.

## Next implementation work

- Resolve model and evaluation artifacts and batch-size/runtime semantics.
- Implement the tutor runner and evaluation against held-out reference answers.
- Define the tutor-to-attention mapping and its limitations.
- Connect the existing gem5 pipeline through the project adapters and CHIA.
- Finalize software candidates and the quality/scoring protocol before optimization campaigns.

The [compute policy](../experiment-contracts/compute-policy/compute-policy.yaml) governs execution tiers. Keep real host resources separate from simulated hardware parameters. Organizer burst remains reserved for the final campaign according to the current policy.
