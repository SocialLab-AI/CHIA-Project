# Full loop implementation checklist

Reference: [implementation proposal](https://docs.google.com/document/d/1V2xZ93ECBvg1yPFOnsgZREtmpG5Drx7ZBAzv0lIf3S4/edit), read 2026-09-15. The user's later scope decision makes the software path inference-only. Retrieval tasks in the proposal are superseded, not pending review.

Base: `orchestration/llm-optimizer` at `a8219a7737eb520e06fb3e961a3eebed903b4a3f`. Local branch: `implementation/deterministic-full-loop`. Antigravity opened locally. The user authorized committing and publishing this branch on 2026-09-15 for server-side acceptance work.

IMPLEMENTED means code exists with the evidence below. PARTIAL means acceptance work remains. TODO means not built. RISK limits execution or interpretation. Local scheduling does not prove remote execution.

| Requirement / proposal phase | Status | Evidence / next work |
|---|---|---|
| 1. Inspect and preserve structure | IMPLEMENTED | Existing runtimes, contracts, scripts, infrastructure and tests inspected; no repository redesign. |
| 2–3. Real graph and nodes (B) | IMPLEMENTED | Validation → mapping → SW/HW → verification → record, using real ChiaFunction bindings. |
| 4. Candidate-driven runners (A) | IMPLEMENTED | Actual Docker/Ollama adapters; installed-service execution still unverified. |
| 5. Knob system (A) | IMPLEMENTED | Immutable candidate, strict schema, fixed/search separation and cross-knob checks. |
| 6. Runtime mappings (A/E) | PARTIAL | gem5 CLI/resolved config and Ollama fields wired; final llama.cpp inference mapper awaits runtime activation. |
| 7. Adam head / YSF worker (B) | IMPLEMENTED | Remote placement and synchronized project imports verified: control/software on Adam and hardware on YSF. |
| 8. Structured logging (A/C) | IMPLEMENTED | Run/candidate/node/worker/timestamps/duration/status, safe errors and output summaries. |
| 9. Combined records (B/C) | IMPLEMENTED | Atomic records with SW/HW knobs/results, source hashes, versions and status. |
| 10. Validation layers (A/C) | IMPLEMENTED | Schema, design space, semantic, preflight, numerical, resolved hardware, metrics and completed records. |
| 11. Failures (C) | IMPLEMENTED | Bounded transient retries, deadlines, per-attempt artifacts and failed records; invalid candidates never retried. |
| 12. Security (C) | PARTIAL | No shell execution, strict paths/JSON, safe logs and isolated containers/CLI settings; deployment permissions need environment checks. |
| 13. Practical containers (C) | IMPLEMENTED | gem5/toolchain Docker; Ollama local service. |
| 14. Local test ladder (B/C) | IMPLEMENTED | Unit, mocked integration, deterministic campaign and actual local CHIA scheduling with runtime fixtures. |
| 15. Combined deterministic execution (B) | PARTIAL | Full local graph passes with fixtures; real services/model/image and approved numerical tolerance required for live run. |
| 16. Gemini CLI without MCP (D) | PARTIAL | Strict CLI boundary exists; mandatory cost-metering policy blocks live activation until metering is implemented. |
| 17. Search controls (D) | PARTIAL | Iteration/wall limits, duplicates, malformed-output fallback, repeated-failure stop and diagnostic Pareto; quality-aware evaluation remains. |
| 18–19. Checklist and explanation | IMPLEMENTED | This checklist and FULL_LOOP.md document ownership, boundaries and evidence. |
| 20. Publication authorization | IMPLEMENTED | User explicitly authorized commit and push after receiving the branch guide. Local checks passed; Adam/YSF deployment remains the next acceptance phase. |
| E. Final inference evaluation | TODO | Pin GGUF, tokenizer budgets and held-out quality protocol; activate and measure final model. |
| E. Proxy calibration | RISK | Whole-program timing includes setup/reference work; attention proxy is not Tutor inference. Numerical tolerance remains explicitly unset. |

## Verification

- Before the scope change: 90 tests passed, including two actual local CHIA/Ray scheduling tests with runtime fixtures.
- After the inference-only change: **87 tests passed** in 24.35 seconds, including both local CHIA/Ray scheduling tests. One upstream Ray FutureWarning; no failed tests. Three obsolete indexing/chunking tests were removed along with their implementation.
- All seven contract files, semantic checks, five rejection checks, manifest agreement and three deterministic candidate validations passed after the change.
- Local Ollama was unavailable. No real gem5 simulation or remote Adam/YSF job was executed in this session.
- Server acceptance evidence: CHIA brought up one head and one gem5 worker; resource placement and project imports passed on both hosts. Both Ollama script invocation styles completed; the warm run reached about 33.35 generated tokens/s and 2.19 seconds total latency. YSF found Docker and the preinstalled `ghcr.io/gem5/devcontainer:v25-1` image. A real simulator execution remains pending.

## Active and legacy paths

- Supported combined entrypoint: `scripts/run_experiment.py`; instructions: [FULL_LOOP.md](FULL_LOOP.md).
- Existing C workload, gem5 configuration and metrics parser are reused. `gem5/run_attention_experiment.py` remains a standalone diagnostic outside the combined loop.
- The old SDK optimizer remains legacy, outside the default controller. Optional CLI activation remains gated by required cost accounting.
- Qwen/Ollama testing ranges remain separate from the fixed Llama inference baseline. No production search ranges were invented.
- Historical example records are illustrative. Synced project sources and the external proposal remain untouched.

## Journal

- 2026-09-15: inspected branch, read proposal, created local branch and opened Antigravity. Built deterministic graph, runtime boundaries, verification, persistence and tests.
- 2026-09-15: removed index/chunk helpers, associated mappings/contracts/search placeholders and review tasks following the user's inference-only decision. Held-out evaluation remains separate from inference prompts.

- 2026-09-15: user authorized publication for server checkout. Verified all 97 documented files match the tested snapshot before this checklist-only update.
- 2026-09-15: Adam/YSF cluster startup and resource placement passed. Added the synchronized project root to head/worker `PYTHONPATH` after YSF correctly rejected the previously missing `src` import.
- 2026-09-15: server rerun verified imports on Adam and YSF, both Ollama entrypoint forms, warm-model inference, Docker access and the installed gem5 image. Next gate is one combined candidate with a reviewed Q4 numerical tolerance.
