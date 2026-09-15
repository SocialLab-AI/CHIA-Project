# Architecture

The current graph, node ownership, runtime boundaries and commands are documented in [FULL_LOOP.md](FULL_LOOP.md). See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for acceptance evidence.

`candidate → validation → mapping → native software + simulated hardware → metrics verification → combined record → decision → next candidate`

Adam owns control and native inference; YSF owns the gem5 worker. CHIA dispatch uses explicit resource labels. Local dispatch uses the same functions without pretending to be distributed execution.

The software workload is inference-only. Native Llama CPU inference remains the final target; a separate Qwen/Ollama profile exercises integration. The attention-kernel proxy executes in gem5. It does not run the Tutor model.

Model-weight quantization and proxy KV-cache format are distinct. Native response latency, simulated time and simulator host runtime remain separate measurements. Held-out reference answers must never enter inference prompts. Gemini proposals must pass deterministic validation before execution.
