# Experiment Evidence

This directory tracks measured experiment evidence separately from architecture and design documents.

## Current baseline evidence

- [`baselines/fp32-attention-kv-cache.md`](baselines/fp32-attention-kv-cache.md) — baseline attention/gem5 execution evidence.

## Folder meaning

- `baselines/` — initial reference runs used to prove correctness and establish comparison points.
- `pilots/` — medium-scale validated campaigns used to measure runtime, cost, failure rate, and methodology.
- `final/` — frozen final experiment campaign used for submission evidence.

## Required information for new experiment records

Each record should contain:

- experiment/run ID
- exact config or config digest
- code/tool provenance
- execution backend/tier
- correctness result
- verified gem5 metrics
- Gemini usage/cost, if applicable
- failure/retry state
- short conclusion

Do not rewrite historical experiment reports to match newer expectations. If the implementation changes materially, create a new run record.
