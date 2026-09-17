# Project overview

The project explores hardware/software co-design for an offline AI Tutor. Its CHIA loop proposes or selects candidate settings, validates them, executes native software and simulated hardware workloads, verifies their metrics, persists one combined record and chooses whether to continue.

The native Tutor runs Qwen2.5 0.5B Instruct with Q5_K_M weights through a loopback llama.cpp server on the control host. Three attributed OpenStax questions provide deterministic required-concept quality evidence. An attention kernel with packed Q4 KV cache remains the gem5 proxy; it does not execute the full Tutor model.

## Current status

| Area | Observed repository state |
|---|---|
| Contracts | Domain JSON schemas, shared definitions, YAML examples and design spaces, and a common validator exist. |
| Hardware path | The candidate-driven Docker/gem5 runner maps validated hardware and workload fields, verifies the resolved simulation and retains metrics plus numerical evidence. Proxy calibration remains partial. |
| Native tutor | The llama.cpp adapter verifies the configured Qwen GGUF identity and evaluates attributed OpenStax questions with deterministic required-concept coverage. |
| Integration | Real CHIA nodes execute validation, mapping, software, hardware, evaluation and record persistence with resource-labelled workers. |
| Search | Hardware knobs plus reviewed temperature/output limits are active; model identity and proxy KV format remain fixed. Deterministic candidates work without Gemini; the optional SDK proposer remains validation-gated. |

See the [configuration guide](configuration.md) for authoritative inputs and the [evidence index](experiments/README.md) for measured reports. Documentation inspection and schema tests are not new simulator execution evidence.

## Next evidence work

- Apply and test the grouped-query mapping and generic head-dispatch corrections described in the [proxy calibration handoff](experiments/proxy-calibration-handoff.md).
- Record the active llama.cpp KV-cache representation independently from model-weight quantization.
- Add dimension-normalized correctness metrics and a Q4 attention region of interest.
- Repeat the corrected five-context proxy sweep before accepting a Qwen-calibrated mapping.
- Expand the held-out Tutor evaluation and review the quality metric before making educational-quality claims.

The [compute policy](../experiment-contracts/policies/compute-policy.yaml) governs execution tiers. Keep real host resources separate from simulated hardware parameters. Organizer burst remains reserved for the final campaign according to the current policy.
