# Issue #60 repeated proxy comparison record

## Record status

| Field | Value |
|---|---|
| Experiment ID | `qwen-proxy-comparison-20260918-01` |
| Execution status | `completed` |
| Compared profiles | `original-corrected` and `qwen-shaped` |
| Contexts | 128, 256, 512, 1024 and 2048 tokens |
| Trials | Three per profile and context |
| Total gem5 jobs | 30 |
| Source revision used by the control checkout | `ebbd7c5` |
| Model SHA-256 | `041474553fcabfc2a2d67903f9d2c2e50bd92528e670da4f33b5d0ce6e59fd55` |
| Native KV cache | F16 keys and F16 values |
| Proxy KV cache | Packed Q4 |
| Final proxy selection | Pending team review |

This document is the durable, repository-side record of the completed Issue
#60 comparison. It transcribes the reviewed structured report and validation
outputs. The generated JSON, checkpoint, plots and full execution log remain
deployment artifacts; their reported hashes are retained below so a later copy
can be verified without committing host-specific raw logs.

## Question and experimental control

The experiment asked whether a Qwen-shaped one-layer attention proxy preserves
the useful native context-growth trend of the smaller original proxy after the
grouped-query mapping and head-dispatch defects were corrected.

Both profiles used the same corrected implementation, hardware configuration,
context sequence, one kernel iteration per trial and three deterministic
trials. Only the attention shape changed:

| Profile | Query heads | KV heads | Head dimension | Layers | Source entry file |
|---|---:|---:|---:|---:|---|
| `original-corrected` | 4 | 2 | 32 | 1 | `gem5/attention_kv_original_proxy.c` |
| `qwen-shaped` | 14 | 2 | 64 | 1 | `gem5/attention_kv_qwen_proxy.c` |

The active shared implementation is `gem5/attention_kv.c`. The named entry
files lock the compared shapes without duplicating the corrected algorithm.

## Pre-execution validation

The operator-side validation completed without scheduling work and reported:

```text
contexts: 128, 256, 512, 1024, 2048
trials_per_context: 3
planned_hardware_jobs: 30
native_kv_cache_types: key=f16, value=f16
validation: passed
execution: not_started
```

A remote worker probe then confirmed that the synchronized worker used the
calibration-aware candidate API:

```text
project_root: /tmp/chia-project
candidate_signature: (value, *, calibration=False)
calibration_mode_present: True
```

The probe contains no credential or host identifier. It proves code-version
alignment at task execution time; it does not by itself prove simulator output.

## Native compile preflight

Both corrected profiles compiled and ran natively at context 16 before the
distributed sweep. `status=PASS` means every reported value was finite. The
calibration path records tolerance violations separately.

| Metric | Original-corrected 4/2/32 | Qwen-shaped 14/2/64 |
|---|---:|---:|
| FP32 checksum | 82.440591351 | -67.540896759 |
| Q4 checksum | 85.843115317 | -18.880343022 |
| Maximum absolute error | 0.026535027 | 0.042213559 |
| MSE | 0.000116079 | 0.000361334 |
| RMSE | 0.010773987 | 0.019008781 |
| Reference RMS | 0.301815590 | 0.361758043 |
| Reference maximum absolute | 0.520577192 | 0.588871658 |
| Normalized RMSE | 0.035697252 | 0.052545565 |
| Normalized maximum error | 0.050972319 | 0.071685500 |
| Mapping | grouped query | grouped query |
| Finite execution status | PASS | PASS |

## Completed repeated comparison

### Summary

| Profile | Shape Q/KV/D | Spearman rho | Normalized-trend MAPE | Reviewed absolute-tolerance violations |
|---|---:|---:|---:|---|
| `original-corrected` | 4/2/32 | 1.0000 | 3.580% | 128 |
| `qwen-shaped` | 14/2/64 | 1.0000 | 3.668% | 128, 256, 512, 1024, 2048 |

The reviewed absolute limits were maximum absolute error `0.01` and MSE
`0.00001`. Calibration retained finite results that exceeded those limits; the
production loop remains fail-closed.

### Original-corrected profile

| Context | Mean gem5 seconds | Stddev | Worst normalized RMSE | Worst normalized maximum error |
|---:|---:|---:|---:|---:|
| 128 | 0.002557000 | 0.000000000 | 0.012966385 | 0.026286831 |
| 256 | 0.004932000 | 0.000000000 | 0.010602555 | 0.020245261 |
| 512 | 0.009470000 | 0.000000000 | 0.009314929 | 0.019847813 |
| 1024 | 0.018943000 | 0.000000000 | 0.009246765 | 0.018456762 |
| 2048 | 0.037634000 | 0.000000000 | 0.009138173 | 0.018569234 |

### Qwen-shaped profile

| Context | Mean gem5 seconds | Stddev | Worst normalized RMSE | Worst normalized maximum error |
|---:|---:|---:|---:|---:|
| 128 | 0.007636000 | 0.000000000 | 0.023581689 | 0.041540401 |
| 256 | 0.014819000 | 0.000000000 | 0.012596505 | 0.029574890 |
| 512 | 0.029393000 | 0.000000000 | 0.010697379 | 0.025396136 |
| 1024 | 0.058514000 | 0.000000000 | 0.009284273 | 0.020225868 |
| 2048 | 0.116700000 | 0.000000000 | 0.009301861 | 0.020398974 |

## Interpretation and decision boundary

**FACT:** All 30 jobs completed. The three simulated-time samples for every
profile/context pair were identical, producing zero standard deviation.

**FACT:** Both profiles preserved the native context ordering with Spearman rho
`1.0`. Their normalized growth curves differed from native Qwen by about 3.6%.

**FACT:** The Qwen-shaped profile matches the selected model's 14 query heads,
2 KV heads and head dimension 64. The smaller profile does not.

**FACT:** The Qwen-shaped profile violated the existing absolute Q4 tolerance
at every context. Its normalized RMSE decreased from about 2.36% at context 128
to about 0.93% at context 2048.

**INTERPRETATION:** The Qwen-shaped profile is structurally more representative
and retains the useful context-scaling behavior. Its approximately three-times
larger simulated time is not a regression measurement because it performs more
modeled work.

**INTERPRETATION:** The 0.088 percentage-point trend-MAPE difference between the
profiles is too small to justify selecting the smaller shape on trend fidelity
alone.

**UNKNOWN:** The native runtime used F16 KV data while the proxy used packed Q4.
The experiment therefore does not establish KV-format equivalence, absolute
latency prediction, complete-model fidelity or native hardware-rank preservation.

**DECISION:** Preserve both profiles. Do not make a final proxy selection in
this branch. Team review should consider an F16 Qwen-shaped comparison, a Q4-only
gem5 region of interest and justified normalized-error acceptance criteria.

Additional repetitions of this unchanged deterministic protocol are not needed;
they would repeat the demonstrated zero-variance result.

## Reported artifact checksums

These hashes were generated by the completed experiment and copied from its
`SHA256SUMS.json`. They describe deployment-local artifacts, not this Markdown
transcription.

| Artifact | SHA-256 |
|---|---|
| `REPORT.md` | `ef83a2493b61b4b06e16c07805529ffeabd3a34894afe196f2d044077851d94c` |
| `checkpoint.json` | `b251b5b64595f398d645dcd26549bf77f02670c6eea3733ad64160d635fa41c2` |
| `normalized-context-trends-original-corrected.svg` | `bbd454b0169543d3e228f10c9fa00babeef443ee61b73b81fa2a2e2a8ab702a0` |
| `normalized-context-trends-qwen-shaped.svg` | `fdd0ece0801c45b6ef66bb77ee65304369b69bdfd105cd557ab3b1494eafc8d0` |
| `proxy-comparison.json` | `cf012ce53fbbabfbbe704a7cb8863aec77d85f41377095ef93a390234b35826a` |

The machine-readable transcription is stored beside this document under
`evidence/qwen-proxy-comparison-20260918-01/summary.transcribed.json`.

## Remaining work before Issue #60 closes

1. Copy or attach the checksum-matching raw result bundle to a durable review location.
2. Measure a Qwen-shaped F16 KV profile or deliberately change and remeasure the native runtime KV format.
3. Add an attention-only gem5 region of interest while retaining whole-program measurements for comparison.
4. Review normalized numerical criteria without weakening the production absolute gate by convenience.
5. Record the team's final proxy decision and update the canonical production profile only after review.
