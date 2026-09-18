# Experiment evidence

| Evidence | Role |
|---|---|
| [Q4 attention baseline](../../gem5/baseline-results.md) | Current repository baseline report; maintained beside the hardware implementation |
| [FP32 attention baseline](fp32-baseline.md) | Historical measured run, preserved unchanged |
| [Qwen–gem5 proxy fidelity protocol](proxy-fidelity.md) | Issue #60 architecture comparison, matched context sweeps, analysis and server procedure |
| [Proxy calibration decision and handoff](proxy-calibration-handoff.md) | Measured outcome, original-versus-revised comparison, discovered defects and remaining acceptance gates |
| [Repeated proxy-profile comparison](proxy-comparison.md) | Equal-iteration, repeated original-corrected versus Qwen-shaped gem5 experiment |
| [Completed proxy comparison result](proxy-comparison-results-20260918.md) | Reviewed 30-job result tables, conclusions, limitations and artifact checksums |

Reports describe the execution recorded in them. They are not proof that later commits, other configurations or the complete tutor loop were executed successfully.

For a new run, preserve its configuration or digest, code/tool revisions, real execution backend, correctness result, metrics with units, usage/cost where applicable, failure state and conclusion. Use the `run_record` definition in the [canonical experiment schema](../../experiment-contracts/schemas/chia-experiment.schema.yaml).

Store generated outputs in the configured results location and link concise reports to their evidence. Add pilot/final subfolders when actual campaigns need them; do not create empty folders in advance. Never rewrite earlier measurements to match newer configurations.
