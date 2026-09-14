# Glossary

| Term | Meaning in this project |
|---|---|
| CHIA loop | Intended repeated propose, validate, execute and evaluate workflow. Project integration is still planned. |
| Candidate | A concrete set of settings selected for evaluation. |
| Schema | Validation rules for document structure and values. |
| Baseline | Reference configuration used for comparison. |
| Design space | Active candidate values, fixed settings, evaluation axes and deferred options. |
| Knob | A configurable setting; only an active search knob may be varied in the current campaign. |
| Tutor | Native Llama 3.2 1B application with retrieval, currently specified but not fully implemented. |
| RAG | Retrieval of supporting content for generation; held-out evaluation answers must remain separate. |
| Attention proxy | Packed Q4 KV-cache attention kernel executed in gem5, representing a limited part of inference computation. |
| Model quantization | Representation of tutor model weights, currently Q4_K_M in the supplied baseline. |
| KV-cache format | Representation of cached attention keys/values; Q4 in the current proxy. |
| Simulated hardware | Target CPU, caches and memory modeled by gem5. |
| Execution backend | Real host/environment running a job; distinct from simulated hardware. |
| Metric | Measured output such as answer quality, time or cache miss rate. |
| Objective | Metric and direction used to compare candidates; scoring details require an agreed evaluation method. |
| Run record | Execution evidence including configuration identity, metrics, execution details and provenance. |
| Runtime ready | Artifacts, supported settings and adapters are resolved; schema validity alone is insufficient. |
| PLANNED / WIRED / TESTED | Intended mapping / implemented connection / supported by a stated check. Always specify which layer and evidence. |

See [configuration](configuration.md) for exact field definitions and [architecture](architecture.md) for component boundaries.
