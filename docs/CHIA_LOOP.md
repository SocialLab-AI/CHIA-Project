# CHIA loop

One candidate follows this path:

1. Validate the closed candidate schema and legal design spaces.
2. Normalize numeric types, serialize canonically, and hash the result.
3. Map software and hardware settings through deterministic code.
4. Dispatch native Qwen and the combined hardware task to their CHIA resources.
5. On the same `gem5` worker, verify the resolved configuration, convert that run's counters into an isolated Accelergy mapping, run McPAT, validate five cache components, and enrich the hardware result with cache dynamic energy.
6. Verify provenance, candidate identity, numerical correctness, metrics, dataset isolation, and energy identity.
7. Emit four minimization objectives and update the Pareto frontier.
8. Persist the run once from the controller and choose the next proposal or stop.

Gemini may propose active knobs but cannot execute tools or author metrics. The random proposer samples without replacement from the same Cartesian space. Both use `run_experiment`, the same nodes, evaluator, record schema, and Pareto code.

Failures are explicit. Invalid candidates are rejected before execution. Energy failures retain the precise `energy_preflight`, `energy_mapping`, `energy_execution`, or `energy_verification` runtime stage inside the failed hardware event. Runtime, metric, identity, and persistence failures create failed records. A campaign with no completed candidate returns an incomplete state and a nonzero CLI exit status. The controller stops on configured budgets or repeated failures.
