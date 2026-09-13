# CHIA Experiment Contracts

Canonical configuration and contract layer for the CHIA offline AI Tutor co-design project.

## Directory Structure

```text
experiment-contracts/
├── README.md
├── schemas/
│   └── chia-experiment.schema.yaml     # Authoritative JSON Schema Draft 2020-12 master contract
├── baselines/
│   ├── tutor.yaml                      # Native AI Tutor software baseline (Llama 3.2 1B Instruct)
│   └── attention.yaml                  # Verified gem5 two-core Q4 KV-cache attention baseline
├── design-spaces/
│   ├── software.yaml                   # AI Tutor software design space (software search pending)
│   └── hardware.yaml                   # Active gem5 attention proxy hardware design space
├── policies/
│   └── compute-policy.yaml             # Host execution tiers, budgets, and backend permissions
└── examples/
    ├── attention-candidate.yaml        # Valid candidate from active cache exploration space
    └── completed-run.yaml              # Verified execution run evidence record
```

## The Master Schema (`schemas/chia-experiment.schema.yaml`)

The canonical schema is a single JSON Schema Draft 2020-12 document serialized as YAML. Its `$defs` block owns the authoritative definitions for all configuration domains:
- `#/$defs/experiment_config` — Joint co-design experiment configuration.
- `#/$defs/tutor_config` — Application-level AI Tutor experiment.
- `#/$defs/attention_experiment` — Concrete gem5 attention proxy experiment.
- `#/$defs/hardware` — gem5 simulated target architecture parameters and constraints.
- `#/$defs/software` — Software configurations (`tutor_software` and `attention_software`).
- `#/$defs/workload` — Workload configurations (`tutor_workload` and `attention_workload`).
- `#/$defs/metrics` — Metrics definitions (`application_metrics`, `gem5_metrics`, and `run_metrics`).
- `#/$defs/objectives` — Multi-objective Pareto optimization targets.
- `#/$defs/design_spaces` — Exploration definitions (`software_design_space` and `hardware_design_space`).
- `#/$defs/compute_policy` — Host compute governance and execution tiers.
- `#/$defs/run_record` — Actual execution evidence record with provenance and metering.

All definitions compose via local JSON pointers (`#/$defs/...`) and resolve completely offline without network access.

## Software Baseline (`baselines/tutor.yaml`)

- **Model**: `Llama 3.2 1B Instruct`
- **Model-weight quantization**: `Q4_K_M`
- **Backend**: `llama.cpp / CPU`
- **CPU threads**: `4` (native tutor CPU threads are independent of the gem5 proxy's 2 threads)
- **Batch size**: `1` (runtime mapping pending; not automatically mapped to llama.cpp `n_batch`)
- **Sampling temperature**: `0.0`
- **Maximum output tokens**: `384`
- **Embedding model**: `MiniLM-L6-dot-v1` (exact repository identifier unresolved)
- **Embedding dimension**: `384`
- **Retrieval method**: `Semantic similarity` (specific distance function unresolved)
- **Top-k**: `2`
- **Chunk size**: `1500` characters (measured in **CHARACTERS**, not tokens)
- **Chunk overlap**: `200` characters (measured in **CHARACTERS**, not tokens; must be `< chunk_size`)
- **Runtime readiness**: `runtime_ready: false` (execution readiness deferred until model artifacts and runtime adapters are implemented)
- **Evaluation guardrail**: Held-out OpenStax evaluation reference answers (`data/references/openstax.json`) are strictly isolated (`reference_source: "openstax"`, `reference_visible_to_model: false`) and must never be visible to the model or ingested into the RAG corpus.

Software search space (`design-spaces/software.yaml`) is recorded as `status: "PLANNED"`; the initial software baseline is fixed for comparison.

## Hardware Baseline & Active Campaign (`baselines/attention.yaml`)

- **CPU model**: `RiscvO3CPU` (active candidates: `RiscvTimingSimpleCPU`, `RiscvO3CPU`)
- **Cores**: `2` (fixed for current campaign; proxy threads = 2)
- **Frequency**: `1 GHz` (active candidates: `1, 2, 3, 4 GHz`)
- **Issue width**: `2` (active candidates: `1, 2, 4`; **constraint**: `RiscvTimingSimpleCPU` requires `issue_width = 1`)
- **L1 I-cache**: `16 KiB`, 2-way, 2-cycle latency (fixed per core)
- **L1 D-cache capacity**: `64 KiB` (active candidates: `16, 32, 64 KiB`, associativity `2, 4, 8`, 2-cycle latency)
- **Shared L2 cache capacity**: `1024 KiB` (active candidates: `256, 512, 1024 KiB`, associativity `4, 8, 16`, 20-cycle latency)
- **Memory**: `DDR3_1600_8x8`, `16 MiB` physical address range (fixed)
- **Mode**: `SE` (gem5 syscall emulation)
- **KV format**: `Q4` (fixed for current campaign; FP16 and Q8 remain future candidates)
- **Workload context tokens**: `512` (evaluation axes: `128, 256, 512`)
- **Query heads**: `4`, **KV heads**: `2`, **Head dimension**: `32`, **Layers**: `1`
- **Repetitions**: `10`, **Warmup runs**: `0`

## Compute Policy Tiers (`policies/compute-policy.yaml`)

Governs real host execution environments, not simulated gem5 targets:
- `dev` — Local / Contabo smoke tests and debugging (max 1 job; Gemini allowed; burst disallowed).
- `integration` — End-to-end integration tests (max 2 jobs; Gemini allowed; burst disallowed).
- `pilot` — Representative benchmarking to validate cost and methodology (max 4 jobs; Gemini allowed; burst disallowed).
- `final` — Frozen campaign on organizer burst resources (max 32 jobs; Gemini allowed; burst allowed).

## Run Records (`examples/completed-run.yaml`)

Stores verified evidence of real executions:
- Execution metrics: `execution_cycles`, `instructions`, `cpi`, `ipc`, `sim_ticks`, `sim_seconds`, `host_seconds`, `l1i_miss_rate`, `l1d_miss_rate`, `l2_miss_rate`, `checksum`, `passed`.
- Gemini API usage metering (`model`, `calls`, `input_tokens`, `output_tokens`, `estimated_cost_usd`).
- Exact provenance (`git_commit`, tool versions, compiler, policy version, seed).

## Metric Separation Principle

- **Application metrics** (`answer_quality` and end-to-end wall-clock `latency_ms`) evaluate the native tutor pipeline.
- **Hardware metrics** (`simulated_seconds`, `cycles_per_core`, `ipc_per_core`, `dram_bandwidth_utilization_percent`) evaluate the gem5 simulated target.
- Wall-clock application latency and simulated gem5 time are distinct metrics and must never be conflated.

## Historical Archive

- The original design document export is preserved in [`docs/archive/CHIA_Experiment_Contracts_v0.2_Architecture.docx`](../docs/archive/CHIA_Experiment_Contracts_v0.2_Architecture.docx) as a labeled historical reference.
