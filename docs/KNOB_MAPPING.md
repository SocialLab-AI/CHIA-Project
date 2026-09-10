# CHIA design parameter and metric mapping

> Issue #11 · Review draft · Runtime bindings PLANNED · 10 September 2026

## Purpose

Define the interface contract for Issue #11 so Yehya, the CHIA loop and Gemini can trace every experiment field to its future implementation and trace measured outputs back to an optimization decision. Change immutable candidate configurations through a validated service; backend adapters alone translate values into simulator or workload settings.

Review basis — 10 September 2026. The clean local checkout is feat/experiment-contracts at 2f94bd87a5b77588075c040a541b0fce25c97e63. A read-only remote lookup confirmed main at 98ee9a9b6d817f84608a9c9e8fad011cbf5d6e94. Inspection of that main tree shows the older config-schema and compute-policy-v0.2 layout, without experiment-contracts. This document targets the updated feature-branch contract, not a verified merge into main. The GitHub connector could not retrieve Issue #11; its title and scope come from the request.

FACT denotes inspected contracts or official documentation. PROPOSED denotes our interface design. UNKNOWN denotes an unresolved binding or measurement definition. All runtime mappings in this document are PLANNED. Existing schema validation is real, but it is not evidence that a knob reaches gem5. Team documentation labels FP32, Q4 and DDR3 validated; no proxy simulation was rerun for this deliverable.

## Architecture

The Tutor LLM is the application being optimized. Gemini proposes candidates. CHIA orchestrates nodes and feedback. gem5 simulates an Attention Kernel proxy. Native application measurements and simulated proxy measurements remain separate.

```mermaid
flowchart TD
  H[Human or Gemini] --> T[Candidate tools and registry]
  S[Schema and active design space] --> T
  T --> V[Validation and capability gate]
  V --> C[Immutable candidate]
  C --> G[gem5 adapter]
  C --> A[Attention adapter]
  G --> R[CHIA execution node]
  A --> R
  R --> O[Raw output and resolved config]
  O --> P[Parser and correctness gate]
  P --> E[Run record and evidence]
  E --> D[Objective and CHIA decision]
  D --> H
```

FACT — CHIA loops express Python data and control flow; ChiaFunction dispatches work using chia_remote and get resolves results. ChiaTool registers typed methods for agent calls. The candidate model, registry, objective policy and six tools below are project interfaces, not verified built-in CHIA design-parameter or objective APIs. Source: CHIA Basics, ChiaFunction and ChiaTool [S1–S3].

| Project layer | Proposed responsibility |
| --- | --- |
| Design parameters | A complete candidate dictionary derived from the experiment schema plus campaign design-space restrictions. |
| Programmatic CHIA edge | Validate → resolve → execute → parse → build record → score. Pass candidate/reference and return structured results. |
| Agentic CHIA edge | Gemini uses an allowlisted ChiaTool wrapper over the same candidate service. |
| Objective decision | A pure score_candidate(record, policy) function rejects ineligible runs, then ranks comparable candidates. CHIA passes this feedback to the next proposal. |
| Resource placement | CHIA worker resources and compute policy place real jobs. hardware.cores describes simulated cores only. |

## Mapping Model

A mapping joins three sources: schema legality, campaign search eligibility and adapter capability. A value must pass all three. The schema may allow context_tokens 1024–4096, but the active campaign permits only 128, 256 and 512 as evaluation conditions. Fixed values still need backend bindings. Compare candidates within the same workload condition.

Declaration convention: attention fields below are in experiment-contracts/attention-experiments/attention-experiment.schema.json. Field hardware.l1d_cache_kib means JSON Pointer #/properties/hardware/properties/l1d_cache_kib. The same dotted-path-to-properties rule applies to every field. Design-space locations refer to experiment-contracts/attention-experiments/design-space.yaml; its declaration is attention-design-space.schema.json. Units are KiB = 1024 bytes and MiB = 1024² bytes.

| ID and backend owner | Proposed module and class |
| --- | --- |
| CPU — gem5 | src/adapters/gem5/cpu.py<br>Gem5CPUAdapter |
| CACHE — gem5 | src/adapters/gem5/cache.py<br>Gem5CacheAdapter |
| MEM — gem5 | src/adapters/gem5/memory.py<br>Gem5MemoryAdapter |
| ATTN — attention workload | src/adapters/attention/adapter.py<br>AttentionAdapter |
| RUN — execution service | src/runners/experiment.py<br>ExperimentRunner |
| CFG — candidate service | src/config/service.py<br>CandidateService |
| MET — metrics service | src/metrics/gem5_parser.py<br>Gem5MetricParser |
| REC — record service | src/metrics/run_record.py<br>RunRecordBuilder |
| TUTOR — native Tutor | src/adapters/tutor/adapter.py<br>TutorAdapter |
| EVAL — native evaluation | src/metrics/tutor_evaluator.py<br>TutorEvaluator |
| POL — compute governance | src/policy/gate.py<br>ComputePolicyGate |

Every module/class above is a proposed destination; none is claimed to exist in the inspected checkout. Method names below resolve through this table. No implementation stubs are included: a passing no-op adapter would create false confidence.

## Knob Mapping Table

Each row includes schema limits, fixed/variable classification, exact design-space source, handler, backend target, dependencies and related metrics. All rows have wiring status PLANNED. Baseline values are recorded independently of schema defaults.

### Hardware knobs

| Field and contract | Planned binding | Constraints and evidence |
| --- | --- | --- |
| hardware.cpu_model<br>VARIABLE  /  RiscvTimingSimpleCPU / RiscvO3CPU<br>Baseline: RiscvO3CPU<br>Source: active_candidates.hardware.cpu_model | CPU: Gem5CPUAdapter.select_model()<br>Target: RISC-V CPU class instances | Allowlist the two schema model names; build must support RISC-V; apply width rule.<br>Related: cycles, IPC, simulated time<br>PLANNED |
| hardware.cores<br>VARIABLE  /  1 / 2 / 4<br>Baseline: 2<br>Source: active_candidates.hardware.cores | CPU: Gem5CPUAdapter.set_cores()<br>Target: CPU instance count and per-core L1 hierarchy | Modeled cores are not Ray CPUs. threads stays 1; extra cores do not imply parallel work.<br>Related: cycles, simulated time<br>PLANNED |
| hardware.frequency_ghz<br>VARIABLE  /  1 / 2 / 3 / 4<br>Baseline: 1<br>Source: active_candidates.hardware.frequency_ghz | CPU: Gem5CPUAdapter.set_frequency()<br>Target: CPU SrcClockDomain.clock | Convert GHz to explicit clock units; record cache/DRAM clock domains; do not silently scale every domain.<br>Related: sim_seconds; cycles interpreted with clock<br>PLANNED |
| hardware.issue_width<br>VARIABLE  /  1 / 2 / 4<br>Baseline: 2<br>Source: active_candidates.hardware.issue_width | CPU: Gem5CPUAdapter.set_issue_width()<br>Target: O3 CPU issueWidth | TimingSimpleCPU requires 1; validate and skip assignment there. Do not set fetch/decode/commit widths implicitly.<br>Related: IPC, CPI, cycles<br>PLANNED |
| hardware.l1i_cache_kib<br>FIXED  /  16<br>Baseline: 16<br>Source: fixed.l1i_cache_kib | CACHE: Gem5CacheAdapter.set_l1i()<br>Target: each core’s L1I instance.size | Convert KiB to bytes using 1024; L2 is total shared capacity. Validate size/line-size/associativity geometry.<br>Related: l1i_miss_rate, cycles, simulated time<br>PLANNED |
| hardware.l1i_associativity<br>FIXED  /  2<br>Baseline: 2<br>Source: fixed.l1i_associativity | CACHE: Gem5CacheAdapter.set_l1i()<br>Target: each core’s L1I instance.assoc | Apply together with capacity; record cache line size and replacement policy.<br>Related: l1i_miss_rate, cycles<br>PLANNED |
| hardware.l1i_latency_cycles<br>FIXED  /  2<br>Baseline: 2<br>Source: fixed.l1i_latency_cycles | CACHE: Gem5CacheAdapter.set_l1i()<br>Target: each core’s L1I instance latency parameters | Unresolved: gem5 separates tag_latency, data_latency, response_latency. Approve a mapping profile; do not call this total hit latency or silently assign all three.<br>Related: l1i_miss_rate, cycles, simulated time<br>PLANNED |
| hardware.l1d_cache_kib<br>VARIABLE  /  16 / 32 / 64<br>Baseline: 64<br>Source: active_candidates.hardware.l1d_cache_kib | CACHE: Gem5CacheAdapter.set_l1d()<br>Target: each core’s L1D instance.size | Convert KiB to bytes using 1024; L2 is total shared capacity. Validate size/line-size/associativity geometry.<br>Related: l1d_miss_rate, cycles, simulated time<br>PLANNED |
| hardware.l1d_associativity<br>VARIABLE  /  2 / 4 / 8<br>Baseline: 4<br>Source: active_candidates.hardware.l1d_associativity | CACHE: Gem5CacheAdapter.set_l1d()<br>Target: each core’s L1D instance.assoc | Apply together with capacity; record cache line size and replacement policy.<br>Related: l1d_miss_rate, cycles<br>PLANNED |
| hardware.l1d_latency_cycles<br>FIXED  /  2<br>Baseline: 2<br>Source: fixed.l1d_latency_cycles | CACHE: Gem5CacheAdapter.set_l1d()<br>Target: each core’s L1D instance latency parameters | Unresolved: gem5 separates tag_latency, data_latency, response_latency. Approve a mapping profile; do not call this total hit latency or silently assign all three.<br>Related: l1d_miss_rate, cycles, simulated time<br>PLANNED |
| hardware.l2_cache_kib<br>VARIABLE  /  256 / 512 / 1024<br>Baseline: 1024<br>Source: active_candidates.hardware.l2_cache_kib | CACHE: Gem5CacheAdapter.set_l2()<br>Target: shared L2 instance.size | Convert KiB to bytes using 1024; L2 is total shared capacity. Validate size/line-size/associativity geometry.<br>Related: l2_miss_rate, cycles, simulated time<br>PLANNED |
| hardware.l2_associativity<br>VARIABLE  /  4 / 8 / 16<br>Baseline: 8<br>Source: active_candidates.hardware.l2_associativity | CACHE: Gem5CacheAdapter.set_l2()<br>Target: shared L2 instance.assoc | Apply together with capacity; record cache line size and replacement policy.<br>Related: l2_miss_rate, cycles<br>PLANNED |
| hardware.l2_latency_cycles<br>FIXED  /  20<br>Baseline: 20<br>Source: fixed.l2_latency_cycles | CACHE: Gem5CacheAdapter.set_l2()<br>Target: shared L2 instance latency parameters | Unresolved: gem5 separates tag_latency, data_latency, response_latency. Approve a mapping profile; do not call this total hit latency or silently assign all three.<br>Related: l2_miss_rate, cycles, simulated time<br>PLANNED |
| hardware.memory_type<br>FIXED  /  DDR3_1600_8x8<br>Baseline: DDR3_1600_8x8<br>Source: fixed.memory_type | MEM: Gem5MemoryAdapter.set_memory()<br>Target: DDR3_1600_8x8 DRAM interface and memory controller | DDR4 excluded. Contract reports DDR3 validated; pin actual gem5 version before wiring.<br>Related: simulated time, cycles<br>PLANNED |
| hardware.memory_size_mib<br>FIXED  /  16<br>Baseline: 16<br>Source: fixed.memory_size_mib | MEM: Gem5MemoryAdapter.set_memory()<br>Target: System memory address range and controller range | 16 × 1024² bytes; includes workload data, code, stack and overhead. Not host RAM or cache capacity.<br>Related: passed; simulated time<br>PLANNED |
| hardware.simulation_mode<br>FIXED  /  SE<br>Baseline: SE<br>Source: fixed.simulation_mode | RUN: ExperimentRunner.set_mode()<br>Target: SE workload/process setup and full_system false | SE is syscall emulation; use timing memory mode for selected CPUs. SE is not a value for mem_mode.<br>Related: passed; all simulator metrics<br>PLANNED |

### Attention software

| Field and contract | Planned binding | Constraints and evidence |
| --- | --- | --- |
| software.implementation<br>FIXED  /  AttentionKernelQuantizedKV<br>Baseline: AttentionKernelQuantizedKV<br>Source: experiment schema const; baseline.attention.yaml | ATTN: AttentionAdapter.select_implementation()<br>Target: Allowlisted attention workload build | Fixed implementation ID; resolve a versioned executable. No arbitrary binary paths.<br>Related: checksum, passed, instructions<br>PLANNED |
| software.kv_format<br>VARIABLE  /  FP32 / Q4<br>Baseline: FP32<br>Source: active_candidates.software.kv_format | ATTN: AttentionAdapter.set_kv_format()<br>Target: K/V storage packing and matching attention/dequantization path | FP32/Q4 active; FP16/Q8 gated. CLI or build flag is not yet established. Q4 is KV representation, not Tutor model quantization.<br>Related: checksum, passed, cycles, cache misses<br>PLANNED |
| software.threads<br>FIXED  /  integer ≥ 1<br>Baseline: 1<br>Source: fixed.threads | ATTN: AttentionAdapter.set_threads()<br>Target: Kernel worker/thread count | Campaign fixed at 1. Schema integer ≥1 is broader; require threads ≤ cores and proven parallel kernel before expansion.<br>Related: passed; simulated time<br>PLANNED |

### Workload controls

| Field and contract | Planned binding | Constraints and evidence |
| --- | --- | --- |
| workload.context_tokens<br>EVALUATION AXIS  /  128 / 256 / 512 / 1024 / 2048 / 4096<br>Baseline: 512<br>Source: evaluation_axes.context_tokens | ATTN: AttentionAdapter.set_shape()<br>Target: K/V sequence length and loop bounds | Validate allocation within 16 MiB. Proposed GQA gate: query_heads divisible by kv_heads. Pin layout, packing and seed; confirm with kernel owner.<br>Related: checksum, passed, instructions, cycles<br>PLANNED |
| workload.query_heads<br>FIXED  /  integer ≥ 1<br>Baseline: 4<br>Source: fixed.query_heads | ATTN: AttentionAdapter.set_shape()<br>Target: Query tensor head count | Validate allocation within 16 MiB. Proposed GQA gate: query_heads divisible by kv_heads. Pin layout, packing and seed; confirm with kernel owner.<br>Related: checksum, passed, instructions, cycles<br>PLANNED |
| workload.kv_heads<br>FIXED  /  integer ≥ 1<br>Baseline: 2<br>Source: fixed.kv_heads | ATTN: AttentionAdapter.set_shape()<br>Target: K/V tensor head count | Validate allocation within 16 MiB. Proposed GQA gate: query_heads divisible by kv_heads. Pin layout, packing and seed; confirm with kernel owner.<br>Related: checksum, passed, instructions, cycles<br>PLANNED |
| workload.head_dimension<br>FIXED  /  integer ≥ 1<br>Baseline: 32<br>Source: fixed.head_dimension | ATTN: AttentionAdapter.set_shape()<br>Target: Per-head vector dimension | Validate allocation within 16 MiB. Proposed GQA gate: query_heads divisible by kv_heads. Pin layout, packing and seed; confirm with kernel owner.<br>Related: checksum, passed, instructions, cycles<br>PLANNED |
| workload.layers<br>FIXED  /  integer ≥ 1 and ≤ 2<br>Baseline: 1<br>Source: fixed.layers | ATTN: AttentionAdapter.set_shape()<br>Target: Number of proxy attention layers | Validate allocation within 16 MiB. Proposed GQA gate: query_heads divisible by kv_heads. Pin layout, packing and seed; confirm with kernel owner.<br>Related: checksum, passed, instructions, cycles<br>PLANNED |

### Measurement controls

| Field and contract | Planned binding | Constraints and evidence |
| --- | --- | --- |
| measurement.repetitions<br>FIXED  /  integer ≥ 1<br>Baseline: 4<br>Source: fixed.repetitions | RUN: ExperimentRunner.set_measurement()<br>Target: Number of measured executions | Fixed 4 in campaign; propose one record per repetition plus a separate summary. Pin ROI and seed.<br>Related: all measured values; variability<br>PLANNED |
| measurement.warmup_runs<br>FIXED  /  integer ≥ 0<br>Baseline: 0<br>Source: fixed.warmup_runs | RUN: ExperimentRunner.set_measurement()<br>Target: Unmeasured warmup executions | Fixed 0. Future warmup must define state preservation and stats reset; separate process warmup is not cache warmup.<br>Related: all performance metrics<br>PLANNED |
| measurement.max_simulation_instructions<br>RUN CONTROL  /  integer or null ≥ 1<br>Baseline: None<br>Source: baseline.attention.yaml (null); no design-space entry | RUN: ExperimentRunner.set_instruction_limit()<br>Target: gem5 instruction-limit exit mechanism | Baseline null; not in design-space fixed block. Non-null requires defined per-core/global semantics; limit exit cannot count as success.<br>Related: instructions, passed; truncation gate<br>PLANNED |

### Identity and lifecycle

| Field and contract | Planned binding | Constraints and evidence |
| --- | --- | --- |
| schema_version<br>METADATA  /  0.2.0<br>Baseline: 0.2.0<br>Source: experiment schema / candidate service; no design-space entry | CFG: CandidateService.manage_candidate()<br>Target: Schema selection | Service-managed metadata; not an optimizer knob. State transitions require evidence. Schema defaults do not fill missing fields.<br>Related: provenance and eligibility; no physical effect<br>PLANNED |
| metadata.experiment_id<br>METADATA  /  string; length ≥ 1<br>Baseline: attn-baseline-001<br>Source: experiment schema / candidate service; no design-space entry | CFG: CandidateService.manage_candidate()<br>Target: Immutable experiment identity | Service-managed metadata; not an optimizer knob. State transitions require evidence. Schema defaults do not fill missing fields.<br>Related: provenance and eligibility; no physical effect<br>PLANNED |
| metadata.campaign_id<br>METADATA  /  string; length ≥ 1<br>Baseline: attention-baseline-v1<br>Source: experiment schema / candidate service; no design-space entry | CFG: CandidateService.manage_candidate()<br>Target: Campaign and comparison cohort | Service-managed metadata; not an optimizer knob. State transitions require evidence. Schema defaults do not fill missing fields.<br>Related: provenance and eligibility; no physical effect<br>PLANNED |
| metadata.description<br>METADATA  /  string; length ≥ 1<br>Baseline: Verified baseline candidate for the attention-kernel gem5 path.<br>Source: experiment schema / candidate service; no design-space entry | CFG: CandidateService.manage_candidate()<br>Target: Human experiment description | Service-managed metadata; not an optimizer knob. State transitions require evidence. Schema defaults do not fill missing fields.<br>Related: provenance and eligibility; no physical effect<br>PLANNED |
| status.state<br>METADATA  /  planned / validated / running / completed / failed / rejected<br>Baseline: validated<br>Source: experiment schema / candidate service; no design-space entry | CFG: CandidateService.manage_candidate()<br>Target: Candidate lifecycle | Service-managed metadata; not an optimizer knob. State transitions require evidence. Schema defaults do not fill missing fields.<br>Related: provenance and eligibility; no physical effect<br>PLANNED |
| status.message<br>METADATA  /  string or null<br>Baseline: Baseline structure reflects the teammate-supplied current configuration; implementation support still governs runnability.<br>Source: experiment schema / candidate service; no design-space entry | CFG: CandidateService.manage_candidate()<br>Target: Validation or lifecycle explanation | Service-managed metadata; not an optimizer knob. State transitions require evidence. Schema defaults do not fill missing fields.<br>Related: provenance and eligibility; no physical effect<br>PLANNED |

Search-space count — the raw hardware product is 5,832. Excluding TimingSimpleCPU widths 2 and 4 leaves 3,888 legal hardware points. FP32/Q4 gives 7,776 candidates per context; three context conditions give 23,328 points and four repetitions would require 93,312 measured executions. These are schema/campaign combinations, not demonstrated runnable configurations or a recommended exhaustive campaign. Start with a small controlled slice.

UNKNOWN — the source design-space schema leaves baseline, fixed and future as generic objects and does not enforce cross-file consistency. The existing validator checks selected baseline semantics, not every generated candidate. A new service must enforce fixed values, active membership, CPU/width compatibility, thread/core compatibility, shape constraints and backend readiness for every candidate.

## Objective and Metric Mapping

Reverse path: workload output and gem5 stats.txt → strict parser → correctness and provenance gates → run-record.schema.json → objective function → CHIA decision → Gemini feedback. Check config.ini/config.json to prove resolved values reached the instantiated simulator. Raw statistic paths depend on gem5 version, CPU model and configured object names [S4].

| Run record metric | Producer and units | Decision role and constraint |
| --- | --- | --- |
| metrics.execution_cycles | CPU numCycles or an explicitly defined ROI cycle counter<br>Unit: cycles<br>MET.parse_stats() | Diagnostic; minimize only at a fixed clock and matched scope. Define per-core versus elapsed-cycle semantics.<br>PLANNED |
| metrics.instructions | simInsts or pinned committed-instruction counters<br>Unit: instructions<br>MET.parse_stats() | Diagnostic; distinguish instructions from micro-ops and include the same ROI/core set as cycles.<br>PLANNED |
| metrics.cpi | Consistent cycles / committed instructions, or verified CPU statistic<br>Unit: cycles/instruction<br>MET.parse_stats() | Diagnostic; denominator must be >0; do not average per-core ratios.<br>PLANNED |
| metrics.ipc | Consistent committed instructions / cycles, or verified CPU statistic<br>Unit: instructions/cycle<br>MET.parse_stats() | Diagnostic; denominator must be >0; validate aggregation semantics.<br>PLANNED |
| metrics.sim_ticks | simTicks from selected ROI interval/dump<br>Unit: ticks<br>MET.parse_stats() | Diagnostic and timing cross-check; never substitute finalTick after reset.<br>PLANNED |
| metrics.sim_seconds | simSeconds; cross-check simTicks / simFreq<br>Unit: simulated seconds<br>MET.parse_stats() | PROPOSED primary objective: minimize within a matched workload condition.<br>PLANNED |
| metrics.l1i_miss_rate | Selected L1I misses / accesses<br>Unit: fraction 0–1<br>MET.parse_stats() | Diagnostic; choose demand or overall consistently and pool counts across included cores.<br>PLANNED |
| metrics.l1d_miss_rate | Selected L1D misses / accesses<br>Unit: fraction 0–1<br>MET.parse_stats() | Diagnostic; zero accesses means unavailable, not zero misses.<br>PLANNED |
| metrics.l2_miss_rate | Shared L2 misses / accesses<br>Unit: fraction 0–1<br>MET.parse_stats() | Diagnostic; one shared-cache scope; no duplicated per-core summation.<br>PLANNED |
| metrics.checksum | Attention workload output<br>Unit: nonempty string<br>ATTN.verify_output() | Evidence identity; a checksum alone does not establish Q4 numerical accuracy.<br>PLANNED |
| metrics.passed | Deterministic correctness comparator and successful completion<br>Unit: boolean<br>ATTN.verify_output() | Hard gate. Require reference agreement under an approved format-specific tolerance and completed workload.<br>PLANNED |

PROPOSED initial objective — among completed, correctness-passing runs with verified bindings and comparable shape/seed/ROI, minimize median sim_seconds over the four measured repetitions. Retain individual records and a versioned campaign summary. Compute baseline_speedup = baseline_median / candidate_median only for positive denominators. Tie handling, failure across repetitions and numerical tolerances must be approved before a campaign; propose excluding any candidate with a failed repetition. No objective field or summary schema currently exists; do not inject them into closed schemas.

Across frequencies, cycles alone are not a time objective. Across FP32 and Q4, validate mathematical accuracy, not byte-identical output. Q4 can alter arithmetic and instruction counts. Cache misses and IPC explain behavior but do not by themselves prove faster or better answers. Energy and area are not measured in this contract and must not be fabricated.

### Run record envelope

All following fields are declared in experiment-contracts/run-records/run-record.schema.json. They are service-owned outputs, not design-space knobs. REC.build_record() is the proposed writer; every runtime binding is PLANNED. The sample completed record contains placeholders and is an example, not run evidence.

| Record field | Schema domain | Producer and meaning |
| --- | --- | --- |
| schema_version | 0.2.0 | Record schema selector; fixed 0.2.0. |
| run_id | string; length ≥ 1 | Unique execution/repetition identity allocated by RUN. |
| experiment.type | ai_tutor / attention_kernel | Candidate type/ID and SHA256 of canonical immutable candidate content. Exclude mutable lifecycle from execution identity only under an explicit versioned digest rule. |
| experiment.experiment_id | string; length ≥ 1 | Candidate type/ID and SHA256 of canonical immutable candidate content. Exclude mutable lifecycle from execution identity only under an explicit versioned digest rule. |
| experiment.config_digest | string; SHA256 digest | Candidate type/ID and SHA256 of canonical immutable candidate content. Exclude mutable lifecycle from execution identity only under an explicit versioned digest rule. |
| execution.tier | dev / integration / pilot / final | RUN captures policy-selected real backend/tier, worker identity, UTC times, attempt and monotonic host elapsed time. host_seconds is not sim_seconds. |
| execution.backend | local / contabo / development_cloud / organizer_burst | RUN captures policy-selected real backend/tier, worker identity, UTC times, attempt and monotonic host elapsed time. host_seconds is not sim_seconds. |
| execution.worker_id | string; length ≥ 1 | RUN captures policy-selected real backend/tier, worker identity, UTC times, attempt and monotonic host elapsed time. host_seconds is not sim_seconds. |
| execution.started_at | string; date-time | RUN captures policy-selected real backend/tier, worker identity, UTC times, attempt and monotonic host elapsed time. host_seconds is not sim_seconds. |
| execution.finished_at | string; date-time | RUN captures policy-selected real backend/tier, worker identity, UTC times, attempt and monotonic host elapsed time. host_seconds is not sim_seconds. |
| execution.attempt | integer ≥ 1 | RUN captures policy-selected real backend/tier, worker identity, UTC times, attempt and monotonic host elapsed time. host_seconds is not sim_seconds. |
| execution.host_seconds | number ≥ 0 | RUN captures policy-selected real backend/tier, worker identity, UTC times, attempt and monotonic host elapsed time. host_seconds is not sim_seconds. |
| usage.gemini.model | string or null | Metered Gemini provider usage and versioned pricing calculation. Unknown cost is not zero; zero calls means real zero usage. Not a hardware objective. |
| usage.gemini.calls | integer ≥ 0 | Metered Gemini provider usage and versioned pricing calculation. Unknown cost is not zero; zero calls means real zero usage. Not a hardware objective. |
| usage.gemini.input_tokens | integer ≥ 0 | Metered Gemini provider usage and versioned pricing calculation. Unknown cost is not zero; zero calls means real zero usage. Not a hardware objective. |
| usage.gemini.output_tokens | integer ≥ 0 | Metered Gemini provider usage and versioned pricing calculation. Unknown cost is not zero; zero calls means real zero usage. Not a hardware objective. |
| usage.gemini.estimated_cost_usd | number ≥ 0 | Metered Gemini provider usage and versioned pricing calculation. Unknown cost is not zero; zero calls means real zero usage. Not a hardware objective. |
| provenance.git_commit | string; length ≥ 7 | Resolved source/tool/build/policy/seed manifest. Actual versions required; reject placeholders before promotion. |
| provenance.chia_version | string; length ≥ 1 | Resolved source/tool/build/policy/seed manifest. Actual versions required; reject placeholders before promotion. |
| provenance.gem5_version | string; length ≥ 1 | Resolved source/tool/build/policy/seed manifest. Actual versions required; reject placeholders before promotion. |
| provenance.kernel_version | string; length ≥ 1 | Resolved source/tool/build/policy/seed manifest. Actual versions required; reject placeholders before promotion. |
| provenance.compiler | string; length ≥ 1 | Resolved source/tool/build/policy/seed manifest. Actual versions required; reject placeholders before promotion. |
| provenance.policy_version | string; length ≥ 1 | Resolved source/tool/build/policy/seed manifest. Actual versions required; reject placeholders before promotion. |
| provenance.seed | integer ≥ 0 | Resolved source/tool/build/policy/seed manifest. Actual versions required; reject placeholders before promotion. |
| status.state | completed / failed / rejected | Terminal execution state and truthful failure reason; success requires completed output and correctness. |
| status.failure_reason | string or null | Terminal execution state and truthful failure reason; success requires completed output and correctness. |

Blocking record gap — metrics are all required and non-null even when status is failed/rejected. A failed launch or unavailable counter cannot honestly populate this schema. Proposed resolution: review a conditional schema allowing unavailable values or a separate failure-event contract. Until approved, retain an internal failure event and raw diagnostics; return an explicit non-rankable tool error. Never emit synthetic zeros or a fake schema-valid completed record.

### Native Tutor boundary

The separate ai-tutor-config/ai-tutor.schema.json remains part of the current contract set. It has no active attention design-space entries. Fields below are native application controls, identity, outputs or proxy references; they are not automatically added to the nine active attention knobs. All proposed handlers are PLANNED.

| Tutor field and role | Schema domain | Planned native binding |
| --- | --- | --- |
| schema_version<br>METADATA | 0.2.0 | CFG.manage_candidate(): schema version, identity, artifact manifest or lifecycle; service-owned. |
| metadata.experiment_id<br>METADATA | string; length ≥ 1 | CFG.manage_candidate(): schema version, identity, artifact manifest or lifecycle; service-owned. |
| metadata.description<br>METADATA | string; length ≥ 1 | CFG.manage_candidate(): schema version, identity, artifact manifest or lifecycle; service-owned. |
| metadata.artifact_manifest<br>METADATA | string or null | CFG.manage_candidate(): schema version, identity, artifact manifest or lifecycle; service-owned. |
| workload.dataset_id<br>EVALUATION CONTROL | string; length ≥ 1 | EVAL.configure_dataset(): versioned questions/corpus/protocol, sample count and seed; freeze within a comparison cohort. |
| workload.corpus_id<br>EVALUATION CONTROL | string; length ≥ 1 | EVAL.configure_dataset(): versioned questions/corpus/protocol, sample count and seed; freeze within a comparison cohort. |
| workload.evaluation_protocol<br>EVALUATION CONTROL | string; length ≥ 1 | EVAL.configure_dataset(): versioned questions/corpus/protocol, sample count and seed; freeze within a comparison cohort. |
| workload.num_questions<br>EVALUATION CONTROL | integer ≥ 1 | EVAL.configure_dataset(): versioned questions/corpus/protocol, sample count and seed; freeze within a comparison cohort. |
| workload.seed<br>EVALUATION CONTROL | integer ≥ 0 | EVAL.configure_dataset(): versioned questions/corpus/protocol, sample count and seed; freeze within a comparison cohort. |
| software.model<br>APPLICATION CONTROL | string; length ≥ 1 | TUTOR.configure(): model/runtime, retrieval, context/generation or batching setting with a runtime capability gate. Pin assets; schema eligibility is not validated support. |
| software.quantization<br>APPLICATION CONTROL | fp32 / fp16 / bf16 / int8 / int4 | TUTOR.configure(): model/runtime, retrieval, context/generation or batching setting with a runtime capability gate. Pin assets; schema eligibility is not validated support. |
| software.retrieval_top_k<br>APPLICATION CONTROL | integer ≥ 1 | TUTOR.configure(): model/runtime, retrieval, context/generation or batching setting with a runtime capability gate. Pin assets; schema eligibility is not validated support. |
| software.max_context_tokens<br>APPLICATION CONTROL | integer ≥ 1 | TUTOR.configure(): model/runtime, retrieval, context/generation or batching setting with a runtime capability gate. Pin assets; schema eligibility is not validated support. |
| software.max_new_tokens<br>APPLICATION CONTROL | integer ≥ 1 | TUTOR.configure(): model/runtime, retrieval, context/generation or batching setting with a runtime capability gate. Pin assets; schema eligibility is not validated support. |
| software.batch_size<br>APPLICATION CONTROL | integer ≥ 1 | TUTOR.configure(): model/runtime, retrieval, context/generation or batching setting with a runtime capability gate. Pin assets; schema eligibility is not validated support. |
| proxy_evaluation.type<br>REFERENCE | attention_kernel | TUTOR.bind_proxy(): versioned mapping and attention candidate reference; no one-to-one model-quantization to KV-format conversion is established. |
| proxy_evaluation.mapping_id<br>REFERENCE | string; length ≥ 1 | TUTOR.bind_proxy(): versioned mapping and attention candidate reference; no one-to-one model-quantization to KV-format conversion is established. |
| proxy_evaluation.attention_experiment_ref<br>REFERENCE | string or null | TUTOR.bind_proxy(): versioned mapping and attention candidate reference; no one-to-one model-quantization to KV-format conversion is established. |
| metrics.application.answer_quality<br>OUTPUT | number or null ≥ 0 | EVAL.measure(): native benchmark output. Keep null until measured; define quality rubric and memory unit convention. Never derive from gem5 proxy time. |
| metrics.application.latency_ms<br>OUTPUT | number or null ≥ 0 | EVAL.measure(): native benchmark output. Keep null until measured; define quality rubric and memory unit convention. Never derive from gem5 proxy time. |
| metrics.application.memory_mb<br>OUTPUT | number or null ≥ 0 | EVAL.measure(): native benchmark output. Keep null until measured; define quality rubric and memory unit convention. Never derive from gem5 proxy time. |
| metrics.application.throughput_qps<br>OUTPUT | number or null ≥ 0 | EVAL.measure(): native benchmark output. Keep null until measured; define quality rubric and memory unit convention. Never derive from gem5 proxy time. |
| status.state<br>METADATA | planned / validated / running / completed / failed / rejected | CFG.manage_candidate(): schema version, identity, artifact manifest or lifecycle; service-owned. |
| status.message<br>METADATA | string or null | CFG.manage_candidate(): schema version, identity, artifact manifest or lifecycle; service-owned. |

Native objectives are proposed separately: maximize answer_quality and throughput_qps; minimize latency_ms and memory_mb under a fixed protocol. Their exact aggregation, rubric and constraints are not specified by the schema. The shared run-record metrics object currently accepts only proxy counters, so it cannot store these native metrics as-is. Keep them in the Tutor metrics.application structure and a separate artifact pending an approved run-record extension.

## Proposed Tool Interface

Expose one candidate service to humans, Gemini and CHIA. Use schema-specific namespaces so software.quantization (Tutor) cannot be confused with software.kv_format (attention). Proposed methods below accept candidate IDs and revisions, not arbitrary file paths or shell commands. The registry is generated from contracts plus explicit adapter routing, avoiding another hard-coded source of legal values.

| Tool signature | Inputs and result | Deterministic behavior |
| --- | --- | --- |
| list_knobs(schema_id, campaign_id) | Returns field, allowed values, units, classification, source, owner, handler and capability status. | Default to active attention knobs; include fixed controls read-only when requested. |
| get_knob(candidate_id, name) | Returns selected value, candidate revision/digest and registry explanation. | Read-only; unknown fields return UNKNOWN_KNOB. |
| set_knob(candidate_id, name, value, expected_revision) | Returns a new candidate revision/digest and a precise diff. | Allow only active fields; deep-copy then validate the whole candidate atomically; original stays unchanged on rejection. |
| validate_candidate(candidate_id, revision) | Returns schema_valid, campaign_valid, runtime_ready, errors and resolved binding plan. | Separate structural validity from readiness. Missing adapter returns BACKEND_NOT_WIRED; no simulation is launched. |
| run_candidate(candidate_id, revision, idempotency_key) | Returns run_id and queued/running/rejected status. | Revalidate immutable snapshot; enforce budget, concurrency and capability gates; launch an allowlisted runner. Same key and digest must not duplicate a run. |
| get_metrics(run_id) | Returns pending, failed or completed envelope plus record/evidence references and eligibility. | Never invent pending metrics; return structured failures for missing or invalid evidence. |

Use typed errors including SCHEMA_INVALID, OUTSIDE_CAMPAIGN, FIXED_PARAMETER, CPU_WIDTH_INCOMPATIBLE, STALE_REVISION, BACKEND_NOT_WIRED, POLICY_DENIED and METRICS_UNAVAILABLE. A multi-field transaction is a future extension; with single-field edits, change issue_width to 1 before switching the baseline O3 CPU to TimingSimpleCPU. Do not silently repair incompatible values.

Record tool actor, parent revision, old/new values, reason and timestamp in an audit sidecar. Proposed src/knobs/registry.py provides lookups; src/knobs/service.py owns transactions and validation. A ChiaTool wrapper registers these methods with self.mcp.add_tool. A runner CHIA node returns an execution handle or terminal result; use CHIA async job patterns for long runs. Keep enforcement in ordinary testable Python so every caller gets identical checks [S2–S3].

### Compute policy dependencies

The existing compute-policy/compute-policy.yaml is operational policy, not simulated hardware. Its schema declarations live in compute-policy.schema.json. All policy fields are administrator-controlled and excluded from set_knob. POL.enforce() is PLANNED; the existing validate_all.py provides static policy checks only.

| Policy field | Current configured value | Planned constraint binding |
| --- | --- | --- |
| policy_version | 0.2.0 | POL.enforce(): validate policy version |
| gemini.budget_usd | 300 | POL.enforce(): meter usage and cumulative budget before Gemini calls |
| gemini.metering_required | True | POL.enforce(): meter usage and cumulative budget before Gemini calls |
| tiers.dev.backends | ['local', 'contabo'] | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.dev.max_parallel_jobs | 1 | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.dev.gemini_allowed | True | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.dev.organizer_burst_allowed | False | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.integration.backends | ['contabo', 'development_cloud'] | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.integration.max_parallel_jobs | 2 | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.integration.gemini_allowed | True | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.integration.organizer_burst_allowed | False | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.pilot.backends | ['contabo', 'development_cloud'] | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.pilot.max_parallel_jobs | 4 | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.pilot.gemini_allowed | True | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.pilot.organizer_burst_allowed | False | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.final.backends | ['organizer_burst'] | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.final.max_parallel_jobs | 32 | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.final.gemini_allowed | True | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |
| tiers.final.organizer_burst_allowed | True | POL.enforce(): enforce backend allowlist, job cap and permission flags for selected tier |

Organizer burst is final-only under current policy; a Gemini tool cannot promote tiers or raise caps. A tier permitting a backend does not automatically authorize a new campaign. These deliverables trigger no paid calls, simulator jobs or policy changes.

## Example End to End Flows

### L1D cache change

Start from the complete baseline record. Clone it under a new experiment ID and planned state. set_knob changes hardware.l1d_cache_kib from 64 to 32. The candidate service checks schema and active membership, then resolves CACHE.set_l1d(size_kib=32, associativity=4, latency_cycles=2). The future adapter assigns 32768 bytes to every per-core L1D cache and applies the approved latency profile. Verify each resolved cache in config.ini before accepting runtime evidence. Parse L1D misses, cycles and simulated time; compare only against baseline repetitions under the same context and ROI.

```python
draft = clone_baseline(new_experiment_id="attn-l1d32-001")
# Proposed pseudocode, not an installed API.
updated = set_knob(draft.id, "hardware.l1d_cache_kib", 32,
                   expected_revision=draft.revision)
check = validate_candidate(updated.id, updated.revision)
# Today: structural checks can pass; runtime_ready is false.
# After adapters are implemented and verified:
if check.runtime_ready:
    job = run_candidate(updated.id, updated.revision, "l1d32-attempt1")
    result = get_metrics(job.run_id)
```

### CPU compatibility rejection

On the baseline, set_knob(cpu_model, RiscvTimingSimpleCPU) must fail because issue_width is 2. Preserve the candidate. First set hardware.issue_width to 1; then set hardware.cpu_model to RiscvTimingSimpleCPU. For TimingSimpleCPU, the width field is a compatibility sentinel, not an O3 issueWidth assignment. For O3, widths 1/2/4 reach issueWidth; other pipeline widths remain explicitly recorded controls.

### Q4 KV representation

Set software.kv_format to Q4 while holding hardware and shape constant. ATTN.set_kv_format must select actual packed KV storage and compatible compute/dequantization logic. Record executable/build/format provenance and verify the output against an approved reference. Then parse the same ROI. The adapter must reject unsupported alignment, packing or memory requirements rather than only changing a label. An FP16 or Q8 request is rejected by the current schema and active-space gate.

### Feedback and failure

A complete, passing four-repetition set produces a median-time comparison in a separate campaign summary. CHIA forwards the result, baseline comparison and diagnostics to Gemini, which proposes the next legal candidate. A timeout, limit exit, missing metric or accuracy failure produces a non-rankable result and preserved evidence. The agent may inspect the error but cannot overwrite passed, rewrite counters or bypass a policy gate.

## Implementation Status

| Component | Observed state | Promotion evidence |
| --- | --- | --- |
| Contract files and validate_all.py | Exist in the inspected feature branch; structural validation is available. | Existing validator and targeted compatibility checks pass; this establishes contract behavior only. |
| Registry, safe tools and adapters | PLANNED; proposed paths and method names only. | WIRED requires a traced candidate-to-target binding and truthful capability errors. |
| Metric parser and objective service | PLANNED; raw stat names, ROI and aggregation not pinned to a project simulator run. | TESTED requires fixtures plus controlled runs, exact resolved config, correctness and source-version evidence. |
| Proxy support | Team contract reports FP32/Q4 and DDR3. Separate gem5/baseline remote-tracking branch exists but was not used as proof of integrated wiring. | Pin the selected backend and audit its code/build before claiming integrated support. |
| Main integration | Remote main verified at 98ee9a9; newer contract layout absent there. | Reconcile the contract branch before adding docs/KNOB_MAPPING.md to main. |

PLANNED means specified but no verified project binding. WIRED means the implementation demonstrably consumes the field and reaches the intended target. TESTED means automated or reproducible integration evidence validates that binding, including negative cases. These uppercase wiring labels are separate from lowercase candidate status.state values such as validated or completed.

## Next Steps

1. Reconcile the feature branch with main and approve this interface document. Confirm final module names with Yehya before coding; preserve the contract paths verified here.

2. Resolve the latency profile, CPU/cache clocks, multicore semantics with a single-thread kernel, kernel argument/build interface, Q4 correctness tolerance, ROI, repetition records and failed-run representation. Pin CHIA and gem5 versions.

3. Implement the pure registry and candidate service first. Check every generated candidate against schema, active space and semantics; test unknown fields, fixed-field edits, stale revisions and CPU-width changes. Treat structural-valid/runtime-unready as an explicit normal state.

4. Wire one vertical slice: baseline → L1D 32 KiB → resolved gem5 config → one verified proxy run → parser → run record. Inspect the real cache instance values and preserve evidence. Add Q4 as the second slice after accuracy verification.

5. Add CHIA nodes and ChiaTool wrappers around the same service, then run a small controlled campaign. Approve objective aggregation and compute tier before expansion. Keep per-run host cost separate from simulated performance.

### Architecture handoff

Thesis: optimize the edge Tutor through a measured attention proxy while keeping native quality evaluation separate. Decision: schema plus active design space constrains candidate tools; adapters own backend translation. Rejected approach: agents editing gem5 source for each experiment, because it loses stable configuration provenance. Open questions: latency meaning, multicore behavior, Q4 accuracy, metric scope and failed-record representation. Next milestone: one evidenced L1D change from candidate to parsed run record.

### Sources and Verification

Project evidence: all experiment-contracts schemas, baseline/example/design-space YAMLs, docs/TEAMMATE_KNOBS.md, docs/ARCHITECTURE.md and scripts/validate_all.py at feature commit 2f94bd87a5b77588075c040a541b0fce25c97e63. Paths are repository-relative. The companion mapping manifest records schema pointers and a source digest for attention-field coverage. Prior conversation: Update Experiment Contracts, 6aa297e2-48c0-83eb-8e20-50e6f45fbeba. Its proposed paths were treated as design ideas and checked against the actual checkout.

S1 — CHIA Basics: https://docs.chialoops.ai/en/latest/getting-started/chia-basics.html

S2 — CHIA ChiaFunction: https://docs.chialoops.ai/en/latest/user_guides/chia_function.html

S3 — CHIA ChiaTool: https://docs.chialoops.ai/en/latest/user_guides/chia_tool.html

S4 — gem5 statistics and resolved configuration: https://www.gem5.org/documentation/learning_gem5/part1/gem5_stats/

S5 — gem5 BaseO3CPU source: https://github.com/gem5/gem5/blob/stable/src/cpu/o3/BaseO3CPU.py

S6 — gem5 Cache source: https://github.com/gem5/gem5/blob/stable/src/mem/cache/Cache.py

Official web references were inspected on 10 September 2026. HEAD/stable documentation is not a pinned backend version. S5 supports the proposed issueWidth target; S6 supports cache capacity, associativity and distinct latency parameters. No installed CHIA/gem5 integration was executed.

Verification performed: exact coverage of 33 attention fields, 24 Tutor fields, 37 run-record fields and 19 policy fields; all six existing example/config validations and semantic policy checks passed. Targeted checks passed for TimingSimpleCPU width 1, rejected width 2, O3 widths 2 and 4, unknown hardware-field rejection and FP16/Q8 rejection. These are schema tests, not runtime adapter tests.
