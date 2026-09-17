# Full loop implementation checklist

Reference: [implementation proposal](https://docs.google.com/document/d/1V2xZ93ECBvg1yPFOnsgZREtmpG5Drx7ZBAzv0lIf3S4/edit), read 2026-09-15. The user's later scope decision makes the software path inference-only. Retrieval tasks in the proposal are superseded, not pending review.

Base: `orchestration/llm-optimizer` at `a8219a7737eb520e06fb3e961a3eebed903b4a3f`. Local branch: `implementation/deterministic-full-loop`. Antigravity opened locally. The user authorized committing and publishing this branch on 2026-09-15 for server-side acceptance work.

IMPLEMENTED means code exists with the evidence below. PARTIAL means acceptance work remains. TODO means not built. RISK limits execution or interpretation. Local scheduling does not prove remote execution.

| Requirement / proposal phase | Status | Evidence / next work |
|---|---|---|
| 1. Inspect and preserve structure | IMPLEMENTED | Existing runtimes, contracts, scripts, infrastructure and tests inspected; no repository redesign. |
| 2–3. Real graph and nodes (B) | IMPLEMENTED | Validation → mapping → SW/HW → verification → record, using real ChiaFunction bindings. |
| 4. Candidate-driven runners (A) | IMPLEMENTED | Qwen llama.cpp and Docker/gem5 adapters are candidate-driven; server acceptance is required after deployment. |
| 5. Knob system (A) | IMPLEMENTED | Immutable candidate, strict schema, fixed/search separation and cross-knob checks. |
| 6. Runtime mappings (A/E) | IMPLEMENTED | gem5 CLI/resolved config and Qwen request fields are wired. GGUF path/hash, context and slots are checked; four server threads remain an explicit startup assertion. |
| 7. Adam head / YSF worker (B) | IMPLEMENTED | Remote placement and synchronized project imports verified: control/software on Adam and hardware on YSF. |
| 8. Structured logging (A/C) | IMPLEMENTED | Run/candidate/node/worker/timestamps/duration/status, safe errors and output summaries. |
| 9. Combined records (B/C) | IMPLEMENTED | Atomic records with SW/HW knobs/results, source hashes, versions and status. |
| 10. Validation layers (A/C) | IMPLEMENTED | Schema, design space, semantic, preflight, numerical, resolved hardware, metrics and completed records. |
| 11. Failures (C) | IMPLEMENTED | Bounded transient retries, deadlines, per-attempt artifacts and failed records; invalid candidates never retried. |
| 12. Security (C) | PARTIAL | No shell execution, strict paths/JSON, safe logs and isolated containers/CLI settings; deployment permissions need environment checks. |
| 13. Practical containers (C) | IMPLEMENTED | gem5/toolchain Docker; llama.cpp remains a local loopback service. |
| 14. Local test ladder (B/C) | IMPLEMENTED | Unit, mocked integration, deterministic campaign and actual local CHIA scheduling with runtime fixtures. |
| 15. Combined deterministic execution (B) | PARTIAL | The earlier Ollama/gem5 candidate completed across Adam/YSF. The final Qwen/llama.cpp plus gem5 campaign still needs one server acceptance run. |
| 16. Gemini SDK without MCP (D) | IMPLEMENTED | Optional metered Google GenAI SDK proposer receives schema-derived fixed/search spaces plus compact history and returns strict JSON for deterministic validation. |
| 17. Search controls (D) | IMPLEMENTED | Iteration/wall/call/cost limits, duplicates, malformed-output fallback, repeated-failure stop, quality-aware objectives and diagnostic Pareto are wired. |
| 18–19. Checklist and explanation | IMPLEMENTED | This checklist and FULL_LOOP.md document ownership, boundaries and evidence. |
| 20. Publication authorization | IMPLEMENTED | User explicitly authorized commit and push. Contract, campaign, unit/integration and opt-in Ray scheduling checks pass for the publication snapshot. |
| E. Final inference evaluation | PARTIAL | Qwen2.5 0.5B Q5_K_M, GGUF hash and initial OpenStax concept scoring are wired; larger held-out evaluation remains future work. |
| E. Proxy calibration | PARTIAL | Issue #60 now has exact GGUF inspection, native/gem5 context sweeps, sensitivity cases, normalized plots and Spearman analysis. Real Adam/YSF evidence and the reviewed post-evidence remapping remain TODO; equivalent native hardware ranking is unavailable on the current cluster. |

## Verification

- Current Qwen/llama.cpp integration: **102 tests passed, 2 scheduling tests skipped** when the explicit local-Ray opt-in was absent. No failed tests.
- All seven contract files, semantic checks, five rejection checks, manifest agreement and three deterministic candidate validations pass.
- Server acceptance evidence: CHIA brought up one head and one gem5 worker; resource placement and project imports passed on both hosts. Both Ollama script invocation styles completed; the warm run reached about 33.35 generated tokens/s and 2.19 seconds total latency. YSF found Docker and the preinstalled `ghcr.io/gem5/devcontainer:v25-1` image.
- Full-loop server acceptance: campaign `adam-ysf-acceptance-20260915-04`, candidate `36decb...d054`, completed in 167.48 seconds. Software completed on Adam in 5.46 seconds; hardware completed on YSF in 164.99 seconds; evaluation completed and the candidate entered the diagnostic Pareto frontier.
- Final runtime smoke evidence: the pinned Qwen2.5 0.5B Instruct Q5_K_M GGUF loaded in llama.cpp on loopback port 8081 and returned a valid OpenAI-compatible response. The final combined Qwen plus gem5 campaign has not yet run.

## Active and legacy paths

- Supported combined entrypoint: `scripts/run_experiment.py`; instructions: [FULL_LOOP.md](FULL_LOOP.md).
- Existing C workload, gem5 configuration and metrics parser are reused. `gem5/run_attention_experiment.py` remains a standalone diagnostic outside the combined loop.
- The optional Google GenAI SDK optimizer is integrated into the controller. Deterministic candidates remain the fallback and default when optimization is disabled.
- Qwen/llama.cpp temperature and output ranges are explicit; model identity, Q5_K_M artifact and service topology remain fixed.
- Historical example records are illustrative. Synced project sources and the external proposal remain untouched.

## Journal

- 2026-09-15: inspected branch, read proposal, created local branch and opened Antigravity. Built deterministic graph, runtime boundaries, verification, persistence and tests.
- 2026-09-15: removed index/chunk helpers, associated mappings/contracts/search placeholders and review tasks following the user's inference-only decision. Held-out evaluation remains separate from inference prompts.

- 2026-09-15: user authorized publication for server checkout. Verified all 97 documented files match the tested snapshot before this checklist-only update.
- 2026-09-15: Adam/YSF cluster startup and resource placement passed. Added the synchronized project root to head/worker `PYTHONPATH` after YSF correctly rejected the previously missing `src` import.
- 2026-09-15: server rerun verified imports on Adam and YSF, both Ollama entrypoint forms, warm-model inference, Docker access and the installed gem5 image. Next gate is one combined candidate with a reviewed Q4 numerical tolerance.
- 2026-09-15: acceptance usage exposed that `--validate-only` checked candidates but not the surrounding campaign document. Full offline campaign validation now runs before Ray initialization and rejects malformed nesting, unsafe endpoints, unknown runtime fields and incomplete correctness tolerances.
- 2026-09-15: the first combined server attempt validated and ran software successfully, but YSF's hardware subprocess exited with code 2 before simulation completed. Failure records now identify the controlled hardware stage and retain only byte-count/hash summaries; raw tool output remains local and omitted.
- 2026-09-15: the stage probe proved the installed `v25-1` gem5 executable rejects `--version` while its image, path, user and entrypoint are valid. Removed that incompatible command; provenance now parses and validates the version banner emitted by the simulator execution that generated the metrics.
- 2026-09-15: the next server attempt compiled and completed gem5, passed its completion, version, shape and numerical checks, then exposed canonical-versus-serialized CPU naming. The verifier now maps `RiscvO3CPU` to gem5's observed `BaseO3CPU` / `gem5::o3::CPU` identity and retains an exact pair for each supported model.
- 2026-09-15: campaign `adam-ysf-acceptance-20260915-04` completed the first real distributed deterministic candidate end to end. The next gate is record/provenance review and model-digest pinning before the three-candidate campaign.
- 2026-09-16: replaced the Ollama adapter with the pinned Qwen2.5 0.5B Instruct Q5_K_M llama.cpp service, added GGUF/build/context/slot preflight, OpenStax questions with evaluator-only references, deterministic concept coverage, schema-aware Gemini output, and final combined-run configuration. The local suite passes; one remote combined acceptance run remains.
- 2026-09-17: implemented the Issue #60 proxy-fidelity protocol without changing the original proxy dimensions: exact GGUF metadata, controlled native and gem5 context sweeps, gem5 sensitivity, normalized trend plot, Spearman context correlation and evidence report. Server execution remains the acceptance gate; native hardware-rank correlation is explicitly unidentifiable on Adam.
