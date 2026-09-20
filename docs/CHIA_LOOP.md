# CHIA loop

One candidate follows this path:

1. Validate the closed candidate schema and legal design spaces.
2. Normalize numeric types, serialize canonically, and hash the result.
3. Map software and hardware settings through deterministic code.
4. Dispatch native Qwen and gem5 work to their CHIA resources.
5. Join the exact gem5 artifact and counters into an isolated energy run.
6. Verify provenance, candidate identity, numerical correctness, metrics, dataset isolation, and energy identity.
7. Emit four minimization objectives and update the Pareto frontier.
8. Persist the run once from the controller and choose the next proposal or stop.

Gemini may propose active knobs but cannot execute tools or author metrics. The random proposer samples without replacement from the same Cartesian space. Both use `run_experiment`, the same nodes, evaluator, record schema, and Pareto code.

Failures are explicit. Invalid candidates are rejected before execution. Runtime, metric, identity, and persistence failures create failed records. A campaign with no completed candidate returns an incomplete state and a nonzero CLI exit status. The controller stops on configured budgets or repeated failures.
