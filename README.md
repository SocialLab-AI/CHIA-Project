# CHIA Qwen hardware/software co-design

This repository contains a bounded CHIA loop for comparing Gemini-guided and seeded-random search over one shared hardware/software design space.

The fixed native workload is Qwen2.5-0.5B-Instruct Q5_K_M evaluated on source-located OpenStax questions. The hardware workload is a packed-Q4 14/2/64 attention proxy in gem5. Each candidate produces separate native latency, proxy simulated time, estimated cache dynamic energy, and quality-loss objectives. Pareto selection preserves those four dimensions.

The 14/2/64 proxy represents Qwen attention geometry for comparative hardware design-space exploration. Its validation supports context-scaling trend fidelity, not absolute full-model latency equivalence. gem5 does not simulate the entire Qwen model.

Start with [the documentation index](docs/README.md). The authoritative campaign contract is [final-burst.yaml](experiment-contracts/campaigns/final-burst.yaml).

```text
experiment-contracts/  schemas, final campaign, design spaces, policy
src/                   deterministic validation, CHIA graph, runtimes, evaluation
gem5/                  attention proxy and gem5 configuration
data/                  OpenStax questions and isolated evaluator references
infra/                 CHIA/Ray deployment templates
scripts/               validation and campaign entry points
docs/                  final architecture, methodology, operations, and limitations
results/               generated evidence; never source data
```
