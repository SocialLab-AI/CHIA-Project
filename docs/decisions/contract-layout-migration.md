# Migration from Legacy Repository Layout to Canonical Experiment Contracts

## Migration Status: Complete

The legacy configuration folders have been consolidated and migrated:
- `config-schema/` (removed)
- `compute-policy-v0.2/` (removed)
- `configs/` (migrated to `experiment-contracts/` and removed)

All experiment contracts are now canonically consolidated in `experiment-contracts/`.

## Target Layout

```text
experiment-contracts/
├── ai-tutor-config/
│   ├── ai-tutor.schema.json
│   ├── example.ai-tutor.yaml
│   ├── design-space.yaml
│   ├── ai-tutor-design-space.schema.json
│   └── README.md
├── attention-experiments/
│   ├── attention-experiment.schema.json
│   ├── attention-design-space.schema.json
│   ├── baseline.attention.yaml
│   ├── design-space.yaml
│   ├── example.candidate.yaml
│   └── README.md
├── compute-policy/
│   ├── compute-policy.schema.json
│   ├── compute-policy.yaml
│   └── README.md
├── run-records/
│   ├── run-record.schema.json
│   ├── example.completed.yaml
│   └── README.md
├── schemas/
│   └── shared.schema.json
├── docs/
│   └── CHIA_Experiment_Contracts_v0.2_Architecture.docx (historical export)
└── README.md
```

## Migration History

1. Initial contracts layout established under `experiment-contracts/`.
2. Hardware contracts updated to gem5 v0.2 with `RiscvO3CPU` / `RiscvTimingSimpleCPU` issue width constraints.
3. Legacy `config-schema/` and `compute-policy-v0.2/` directories removed.
4. Active Q4 hardware campaign and emitted metrics consolidated into `attention-experiments/`.
5. User-supplied software baseline (Llama 3.2 1B Instruct, Q4_K_M, llama.cpp / CPU, MiniLM-L6-dot-v1) consolidated into `ai-tutor-config/`.
6. Legacy `configs/` migrated and removed; single validation entrypoint established at `scripts/validate_configs.py`.
