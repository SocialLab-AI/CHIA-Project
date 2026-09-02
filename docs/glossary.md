# CHIA Hackathon: Glossary

> Working reference. One-line defs. Schema field definitions live in `schema/`, not here.

## CHIA core

| Term | Definition |
|------|------------|
| **CHIA loop** | A directed cyclic graph of tasks that repeatedly tests and improves SW/HW configurations using measured feedback. |
| **Node** | One unit of work in the loop — e.g. running the tutor, running gem5, quality evaluation, or energy estimation. |
| **Edge** | A connection between nodes that carries control, dependencies, data, or results. |
| **Programmatic edge** | An edge where the program explicitly decides the next step. |
| **Agentic edge** | An edge where the AI agent decides which MCP tool or action to run next. |
| **Cluster** | The machines and logical workers that provide the resources to execute the loop. |
| **MCP tool** | A capability exposed over MCP that the agent can call — e.g. running gem5 or reading experiment metrics. |

## Our flow

| Term | Definition |
|------|------------|
| **Edge AI tutor** | An offline sub-1B RAG tutor that answers school questions locally using a small LLM and embedding-based retrieval. |
| **gem5 proxy workload** | Representative GEMM kernels and SimPoint regions, simulated instead of full LLM inference. |
| **SW knobs** | Software settings CHIA can change: quantization level, retrieval top-k, batch size. *(lock the list in Phase 1)* |
| **HW knobs** | gem5 settings CHIA can change: L1/L2 cache sizes, issue width, CPU core count. *(lock the list in Phase 1)* |
| **Objective / metric fusion** | The combined optimization target balancing answer quality against latency, energy, and memory. |
| **Quality metric** | Tutor-answer quality scored on a fixed OpenStax QA benchmark with a fixed grader model. |
| **Cost / compute metrics** | Per-run efficiency logged for every run: latency, memory, energy, wall-clock runtime, compute cost. Graded, so it's a deliverable. |

## Process

| Term | Definition |
|------|------------|
| **Config schema** | The shared configuration contract in `schema/` that defines valid experiment settings and fields. |
| **Owner / reviewer** | Every issue has one owner and one reviewer from a different stream before integration. |