# Qwen attention proxy calibration: decision and developer handoff

This document records the evidence collected for Issue #60, the defects exposed by the Qwen-shaped pilot, the current scientific conclusion and the remaining implementation work. It is written as a continuation point for a developer who did not participate in the experiment.

The proxy is a deterministic attention microbenchmark executed in gem5. It is not a simulation of complete Qwen inference. Native Qwen metrics and gem5 proxy metrics must remain separate in reports and optimization records.

The tables below transcribe the completed run outputs reviewed during the investigation. Generated result directories are intentionally excluded from source synchronization and Git. Before Issue #60 is closed, publish or attach the reviewed, non-sensitive JSON/report/checksum bundle so the measurements can be audited independently of this narrative.

## Current decision

**PARTIAL — retain and calibrate the proxy.**

Keep the proxy as a one-layer attention workload for comparing simulated hardware candidates. Do not use its simulated seconds as a prediction of complete Qwen latency. The original proxy produced strong context-scaling evidence, but its dimensions and KV-head mapping did not represent the selected Qwen model. A Qwen-shaped pilot improved structural fidelity and exposed two real kernel defects. The canonical kernel now contains the mapping and dispatch corrections plus relative-error output. The repeated corrected comparison still requires distributed execution before the proxy can be labelled Qwen-calibrated.

```text
Exact Qwen GGUF
      |
      +--> architecture profile: 24 layers, 14 query heads,
      |    2 KV heads, head dimension 64
      |
      +--> native llama-bench context sweep ------------------+
                                                            compare normalized trends
Original 4/2/32 proxy --> gem5 context sweep ----------------+
      |
      +--> Qwen-shaped 14/2/64 pilot
              |
              +--> exposed grouped-query mapping defect
              +--> exposed incomplete head dispatch
              +--> corrected one-context pilot
              +--> full corrected sweep still required
```

## Evidence classification

**FACT:** The model profile came from the SHA-verified GGUF header. The selected artifact reported Qwen2 architecture, 24 layers, hidden size 896, 14 query heads, 2 KV heads, head dimension 64, intermediate dimension 4864, maximum context 32768 and Q5_K_M weight quantization.

**FACT:** Q5_K_M describes model weights. It does not establish the runtime KV-cache type used by llama.cpp.

**FACT:** The original proxy and native context sweeps completed at 128, 256, 512, 1024 and 2048 tokens. A separate Qwen-shaped pilot completed only at 128 tokens.

**INTERPRETATION:** Similar normalized context growth supports using the proxy to study relative attention scaling. It does not establish absolute timing equivalence, full-model fidelity or hardware-ranking preservation.

**IDEA:** After the kernel defects and measurement limitations are corrected, use the proxy to rank legal gem5 hardware candidates while native Qwen measures application latency and answer quality.

**UNKNOWN:** The revised-proxy context trend, measured dimension-normalized error and native-versus-gem5 hardware-rank preservation remain unverified. Native llama-bench reported F16 K/V; the separately launched llama.cpp service did not explicitly override its cache types, so its startup evidence should still be retained.

## Phase 1: exact model profiling

`src/tutor/model_profile.py` reads the GGUF metadata and rejects a file whose SHA-256 differs from the configured artifact. The profiled model reported:

| Field | Measured value |
|---|---:|
| Architecture | `qwen2` |
| Model | Qwen2.5 0.5B Instruct |
| Weight quantization | `Q5_K_M` |
| Transformer layers | 24 |
| Hidden size | 896 |
| Query heads | 14 |
| KV heads | 2 |
| Head dimension | 64 |
| Intermediate dimension | 4864 |
| Maximum context | 32768 |
| Parameters derived from tensor shapes | 630,167,424 |
| KV-cache quantization | Runtime-dependent; not yet recorded |

## Phase 2: native Qwen context sweep

`src/tutor/benchmark.py` used CPU-only `llama-bench` prompt processing. The timing excludes model loading, tokenization and sampling. CPU utilization and process memory cover the benchmark process rather than only the attention operation.

| Context tokens | Average latency (ms) | Tokens/s | Peak RSS (MiB) | CPU utilization | Normalized latency |
|---:|---:|---:|---:|---:|---:|
| 128 | 1,699.615 | 75.495 | 563.27 | 338% | 1.000x |
| 256 | 3,093.635 | 83.262 | 572.50 | 350% | 1.820x |
| 512 | 6,270.443 | 81.666 | 595.29 | 354% | 3.689x |
| 1024 | 12,851.833 | 79.761 | 601.80 | 358% | 7.562x |
| 2048 | 27,646.246 | 74.138 | 614.73 | 358% | 16.266x |

Linux `perf` counters were unavailable for this run. The missing counters must remain recorded as unavailable rather than inferred.

## Phase 3: original proxy sweep

The original workload used 4 query heads, 2 KV heads, head dimension 32, one representative layer, two host threads, ten kernel repetitions and packed-Q4 KV data. gem5 simulated a two-core RISC-V O3 system. Its timing scope included setup, FP32 reference work, thread management and Q4 work.

| Context tokens | Simulated seconds | Normalized time | Maximum absolute error | MSE | Within reviewed tolerance? |
|---:|---:|---:|---:|---:|---|
| 128 | 0.004594 | 1.000x | 0.010727912 | 0.000012264 | No |
| 256 | 0.009023 | 1.964x | 0.008107156 | 0.000008394 | Yes |
| 512 | 0.016121 | 3.509x | 0.007946730 | 0.000006495 | Yes |
| 1024 | 0.035507 | 7.729x | 0.007124960 | 0.000006097 | Yes |
| 2048 | 0.070729 | 15.396x | 0.007380873 | 0.000006133 | Yes |

The reviewed limits were maximum absolute error `0.01` and MSE `0.00001`. Four of five contexts passed; the 128-token case exceeded both limits slightly. The calibration workflow retained this finite failure as evidence, while the production loop remained fail-closed.

The native and proxy context ordering had Spearman rho approximately `1.0`. Their normalized curves differed by roughly 4–5% on average, depending on whether the shared 128-token baseline point is included. This is useful context-scaling evidence. Both series are monotonic, so rank correlation alone is weak; the similar normalized magnitudes provide the stronger observation.

The simulated hardware sensitivity cases ranked, from fastest to slowest:

1. high-associativity
2. baseline
3. compact-cache

No equivalent native hardware ranking exists because the native host cannot expose the same cache sizes, associativities, issue width and memory controller. This ranking is therefore a gem5-proxy result only.

## Phase 4: Qwen-shaped pilot and discovered defects

The pilot changed only the modeled attention shape and experiment cost:

```yaml
context_tokens: 128
query_heads: 14
kv_heads: 2
head_dimension: 64
layers: 1
threads: 2
repetitions: 1
kv_format: Q4
```

The pilot was executed through a temporary operator script. Its source changes are not yet part of the canonical repository kernel.

### Defect 1: incorrect grouped-query mapping

The kernel selected a KV head with:

```c
query_head % KV_HEADS
```

That alternates KV heads. Qwen's 14 query heads and 2 KV heads require seven consecutive query heads per KV head:

```text
query heads 0..6   -> KV head 0
query heads 7..13  -> KV head 1
```

The general mapping is:

```c
int query_heads_per_kv = QUERY_HEADS / KV_HEADS;
int kv_head = query_head / query_heads_per_kv;
```

The candidate validator and C workload must reject a shape where `QUERY_HEADS % KV_HEADS != 0`.

### Defect 2: incomplete attention-head dispatch

The Q4 main thread directly executed heads 0 and 2, while the worker handled odd-numbered heads. This covered all heads only when `QUERY_HEADS == 4`. With 14 heads, even heads 4, 6, 8, 10 and 12 were never calculated.

The temporary correction passed main-thread identifier zero through the same generic head-striding worker used by the other thread. That allowed the two threads to cover every head.

## Before-and-after pilot evidence

| Metric at context 128 | Original 4/2/32 proxy | Qwen-shaped pilot before dispatch fix | Qwen-shaped pilot after mapping and dispatch fixes |
|---|---:|---:|---:|
| Query heads / KV heads / head dimension | 4 / 2 / 32 | 14 / 2 / 64 | 14 / 2 / 64 |
| Repetitions | 10 | 1 | 1 |
| Maximum absolute error | 0.010727912 | 0.546621978 | 0.022706896 |
| Mean squared error | 0.000012264 | 0.045505238 | 0.000070914 |
| Simulated seconds | 0.004594 | 0.007523 | 0.007520 |
| Instructions | 7,957,524 | 7,065,462 | 8,685,920 |
| Aggregate IPC | 1.7322 | 1.0917 | 1.1561 |
| L2 miss rate | 0.7603 | 0.8542 | 0.8447 |
| Within the original absolute tolerance | No | No | No |

Fixing head dispatch reduced maximum error by approximately 24 times and MSE by approximately 642 times relative to the broken Qwen-shaped pilot. Compared with the smaller original proxy, the corrected Qwen-shaped pilot still had about 2.1 times the maximum error and 5.8 times the MSE.

The revised proxy is therefore structurally better and numerically unresolved. The higher absolute error does not by itself prove that the revised proxy is less useful: it covers more heads and twice the head dimension, while the tolerance is absolute and may not be dimension-neutral. Do not loosen the tolerance until relative error and the runtime KV format are measured.

The timing and instruction rows are not a fair optimization comparison because the original and revised workloads have different shapes and repetition counts, and the gem5 measurement includes initialization and FP32 reference work.

## Canonical implementation and remaining work

Current status:

1. **IMPLEMENTED:** `gem5/attention_kv.c` uses validated grouped-query mapping in FP32 and Q4 paths.
2. **IMPLEMENTED:** both threads use generic strided head dispatch, covering every legal query head.
3. **IMPLEMENTED:** production validation remains fixed while an explicit calibration-only path accepts only reviewed 4/2/32 and 14/2/64 shapes with one iteration.
4. **IMPLEMENTED:** unit tests cover the calibration boundary, both compile mappings, relative parsing and repeated-trial aggregation.
5. **IMPLEMENTED:** correctness output and parsing include reference RMS, RMSE, normalized RMSE, reference maximum magnitude and normalized maximum error.
6. **PARTIAL:** native llama-bench recorded F16 K/V. Preserve the llama.cpp service startup evidence to confirm its effective cache defaults independently.
7. **TODO:** add an m5 region of interest around quantized attention so performance counters can exclude initialization, FP32 reference calculation and thread setup. Retain whole-program metrics for backward comparison.
8. **TODO:** compile and run both corrected shapes natively on the Linux execution host.
9. **TODO:** run `scripts/run_proxy_comparison.py` for three trials at contexts 128, 256, 512, 1024 and 2048.
10. **TODO:** review and publish the new report, JSON, SVGs and checksum manifest while retaining the original bundle unchanged.

## Acceptance gates

The revised proxy can be labelled **Qwen-shaped** after the mapping, dispatch and divisibility checks are merged and tested.

It can be labelled **context-calibrated** only after the revised five-context sweep preserves the native ordering and has a reviewed bound on normalized trend deviation.

It can be labelled **numerically accepted** only after the team reviews dimension-normalized error and selects a justified tolerance. Passing must not be created by raising the old limit without analysis.

It cannot be labelled a **full-model simulator** under this design. It excludes projections, MLP blocks, embeddings, all-layer repetition, tokenization, sampling, llama.cpp scheduling and complete model-weight access.

It cannot claim **native hardware-rank preservation** without measurements on equivalent configurable native hardware or another independently justified validation method.

## File ownership and continuation map

| File | Responsibility |
|---|---|
| `gem5/attention_kv.c` | FP32 reference, packed-Q4 attention kernel, threading and correctness output |
| `src/hardware/attention_kernel.py` | Maps canonical workload fields to C compile definitions |
| `src/hardware/runner.py` | Builds and runs the kernel in isolated Docker/gem5, parses correctness and verifies executed shape |
| `src/hardware/proxy_fidelity.py` | Builds architecture comparisons, normalized trends, sensitivity ordering and reports |
| `src/tutor/model_profile.py` | Extracts SHA-verified model architecture from GGUF metadata |
| `src/tutor/benchmark.py` | Runs controlled native llama-bench context measurements |
| `scripts/run_proxy_fidelity.py` | Executes profile, native, hardware and analysis phases |
| `experiment-contracts/testing/proxy-fidelity.server.example.yaml` | Portable operator configuration example |
| `docs/experiments/proxy-fidelity.md` | Reproducible execution protocol |
| This document | Decision history, measured results, defects and remaining gates |

## Final reporting rule

Future reports should use language such as:

> The gem5 workload is a Qwen-shaped, single-layer attention proxy used to compare simulated hardware candidates. Native Qwen measurements provide application-level latency and quality. The two metric domains are evaluated together by the CHIA loop but are not treated as equivalent measurements.

Do not state that gem5 runs Qwen, that proxy seconds predict complete inference latency, or that the current sensitivity ranking has been reproduced on native hardware.
