# CHIA Attention-Kernel Compute Policy + Schema Split (v0.2)

This branch package proposes a practical execution-governance layer for the CHIA / A³ MICRO 2026 project after the workload direction moved to an **attention kernel**.

The core design decision is to separate three concerns that were previously mixed in one experiment record:

1. **Experiment configuration** — what scientific candidate is being tested.
2. **Compute policy** — where the project is allowed to run, how far it may scale, and how Gemini spending is bounded.
3. **Run record** — what actually happened: backend, metrics, cost, provenance, and status.

This prevents a simulated hardware knob such as `hardware.l1_cache_kb` from being confused with the real host machine that runs gem5.

## Files

- `schemas/experiment.schema.json` — immutable attention-kernel candidate input.
- `schemas/compute-policy.schema.json` — CP-01 progressive compute policy.
- `schemas/run-record.schema.json` — measured execution/result/provenance record.
- `configs/compute-policy.yaml` — proposed default policy for the team.
- `examples/experiment.dev.yaml` — tiny smoke-test candidate.
- `examples/experiment.pilot.yaml` — pilot candidate example.
- `examples/run-record.completed.yaml` — completed result example.
- `scripts/validate_configs.py` — validates all examples and checks policy budget consistency.
- `docs/ARCHITECTURE.md` — architecture rationale and tier behavior.
- `docs/MIGRATION_v0.1_to_v0.2.md` — what changes from the original AI-Tutor-oriented schema.
- `docs/DECISION_CP-01.md` — concise project decision record.
- `BRANCH_GUIDE.md` — exact commands to add these files in a Git branch.

## Important status

The attention-kernel field names and ranges are **proposed v0.2 contract**, not a claim that every knob is already wired to the chosen kernel or gem5 model. Before freezing the schema, verify each knob has a real implementation mapping and measurable effect.

## Validate locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/validate_configs.py
```

Expected result:

```text
PASS experiment.dev.yaml
PASS experiment.pilot.yaml
PASS run-record.completed.yaml
PASS compute-policy.yaml
PASS semantic policy checks
```
