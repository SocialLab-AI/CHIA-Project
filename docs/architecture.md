# Architecture

The current graph, node ownership, runtime boundaries and commands are documented in [FULL_LOOP.md](FULL_LOOP.md). See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for acceptance evidence.

`candidate → validation → mapping → native software + simulated hardware → metrics verification → combined record → decision → next candidate`

Adam owns control and native inference; YSF owns the gem5 worker. CHIA dispatch uses explicit resource labels. Local dispatch uses the same functions without pretending to be distributed execution.

The software workload is inference-only. Qwen2.5 0.5B Q5_K_M runs natively through a loopback llama.cpp server on Adam. The attention-kernel proxy executes in gem5 and does not run the Tutor model.

Model-weight quantization and proxy KV-cache format are distinct. Native response latency, simulated time and simulator host runtime remain separate measurements. Held-out reference answers must never enter inference prompts. Gemini proposals must pass deterministic validation before execution.
