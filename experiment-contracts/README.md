# Experiment contracts

The machine-readable source of truth consists of:

- `campaigns/final-burst.yaml`: runtime limits, resources, study parity, pilot budget, and stopping rules.
- `design-spaces/software.yaml`: active and fixed native knobs.
- `design-spaces/hardware.yaml`: active and fixed proxy/hardware knobs.
- `baselines/tutor.yaml`: Qwen and OpenStax workload contract.
- `baselines/attention.yaml`: unmeasured 14/2/64 production proxy baseline.
- `schemas/chia-experiment.schema.yaml`: closed candidate, record, and supporting schemas.
- `policies/compute-policy.yaml`: reviewed compute and estimated Gemini pricing limits.

Candidate identity is generated only after validation and numeric type normalization. Runtime records must join software, gem5, and energy results to the same candidate; the energy record also binds to the exact hardware-result digest and stats hash.

The OpenStax reference answers are evaluator-only and never enter the model prompt. The committed production baseline contains no fabricated run metrics.
