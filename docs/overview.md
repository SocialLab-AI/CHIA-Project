# Project overview

The project explores hardware/software co-design for an offline AI Tutor. The intended CHIA loop proposes candidate settings, validates them, executes workloads, and compares measured outcomes. The complete automated loop is still under development.

The native tutor baseline specifies Llama 3.2 1B Instruct with Q4_K_M weights, llama.cpp on CPU, and MiniLM-L6-dot-v1 retrieval. An attention kernel with packed Q4 KV cache is the gem5 proxy. It does not execute the full tutor model or establish tutor answer quality.

## Current status

| Area | Observed repository state |
|---|---|
| Contracts | Domain JSON schemas, shared definitions, YAML examples and design spaces, and a common validator exist. |
| Hardware path | Executable workload, gem5 configuration, runner, and metric extraction exist under `gem5/`. The repository records a Q4 baseline run. |
| Native tutor | Baseline is specified; runtime readiness is false. Model artifacts and adapter implementation remain unresolved. |
| Integration | `src/` provides interfaces; the hardware/tutor runners and CHIA entrypoint still contain unimplemented boundaries. |
| Search | Seven hardware parameters are active; core count and proxy Q4 remain fixed. Software search ranges are pending. |

See the [configuration guide](configuration.md) for authoritative inputs and the [evidence index](experiments/README.md) for measured reports. Documentation inspection and schema tests are not new simulator execution evidence.

## Next implementation work

- Resolve model, embedding, and corpus artifacts and batch-size/runtime semantics.
- Implement the tutor runner and evaluation against held-out reference answers.
- Define the tutor-to-attention mapping and its limitations.
- Connect the existing gem5 pipeline through the project adapters and CHIA.
- Finalize software candidates and the quality/scoring protocol before optimization campaigns.

The [compute policy](../experiment-contracts/compute-policy/compute-policy.yaml) governs execution tiers. Keep real host resources separate from simulated hardware parameters. Organizer burst remains reserved for the final campaign according to the current policy.
