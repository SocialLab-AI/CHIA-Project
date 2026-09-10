# Migration from Legacy Repository Layout

## Migration Status: Complete

The legacy split folders have been removed from this branch:
- `config-schema/` (removed)
- `compute-policy-v0.2/` (removed)

All experiment contracts are now consolidated in `experiment-contracts/`.

## Target Layout

```text
experiment-contracts/
├── ai-tutor-config/
├── attention-experiments/
├── compute-policy/
├── run-records/
├── docs/
└── scripts/
```

## Migration History

1. Initial layout established under `experiment-contracts/`.
2. Hardware contracts updated to gem5 v0.2 with `RiscvO3CPU` / `RiscvTimingSimpleCPU` issue width constraints.
3. Legacy `config-schema/` and `compute-policy-v0.2/` directories removed.
