# Final confirmatory Gemini-versus-random campaign

This directory publishes the reviewed compact evidence from the final
confirmatory CHIA comparison executed on 2026-09-22. Gemini 3.8 Flash and
seeded random search each evaluated ten candidates through the same native
Qwen, gem5 attention-proxy, cache-energy, quality, record, and Pareto pipeline.

## Outcome

All 20 candidates completed and were feasible. The stored campaign frontiers
matched independent recomputation, both campaign manifests passed, and the
combined four-objective frontier contains seven candidates: six proposed by
Gemini and one proposed by random search.

| Field | Gemini | Random |
| --- | ---: | ---: |
| Evaluated candidates | 10 | 10 |
| Completed candidates | 10 | 10 |
| Campaign Pareto candidates | 6 | 7 |
| Combined-frontier contribution | 6 | 1 |
| Campaign wall time | 9894.058 s | 10414.080 s |
| Proposer | `gemini-3.8-flash` | Seed `20260922` |
| Proposal failures | 0 | 0 |

Gemini used 45,187 tokens over ten accepted requests. The recorded USD
0.07756725 cost is an estimate from the configured pricing policy, not verified
live billing.

## Objective winners

| Objective | Candidate | Method | Best observed value |
| --- | --- | --- | ---: |
| Native Qwen latency | `588ef56fbc16...` | Gemini | 1242.817 ms |
| gem5 proxy simulated time | `c12f1db945bd...` | Gemini | 0.019288 s |
| Estimated cache dynamic energy | `6ab534d518fb...` | Gemini | 6553.915 uJ |
| Exact option-text accuracy | `3fbd6776d457...` | Random | 44.4% (111/250) |

No candidate minimizes all four objectives. The project does not collapse the
measurements into an arbitrary weighted score.

## Preferred best-observed candidate

Candidate
`588ef56fbc16fa8f5a74c5075ba2357f8bce41b21083cfc93ae367d701bd48b5`
is the preferred best-observed candidate for a native-latency-prioritized use
case. It produced the lowest observed native Qwen latency while remaining on
the combined Pareto frontier and retaining competitive quality, proxy time,
and estimated cache dynamic energy.

| Domain | Setting or result |
| --- | --- |
| Native model | Qwen2.5 0.5B Instruct, Q5_K_M, llama.cpp CPU |
| Software knobs | Temperature 0; maximum output 128 tokens; 4 threads; batch 1 |
| CPU proxy knobs | RiscvO3CPU; 2 cores; 4 GHz; issue width 2 |
| L1 instruction cache | 16 KiB; 2-way; 2-cycle latency |
| L1 data cache | 16 KiB; 2-way; 2-cycle latency |
| Shared L2 cache | 256 KiB; 4-way; 20-cycle latency |
| Memory | DDR3_1600_8x8; 16 MiB |
| Attention proxy | 14 query heads; 2 KV heads; head dimension 64; context 512 |
| Proxy repetitions | 10 |
| Native latency | 1242.816940 ms |
| Proxy simulated time | 0.022916 s |
| Estimated cache dynamic energy | 6977.288508 uJ |
| Exact option-text accuracy | 44.0% (110/250) |

This is a preference decision, not a mathematical overall optimum. Candidate
`6ab534d518fb...` has the same native software knobs and achieved lower cache
energy plus a faster proxy result. The observed native-latency difference
between those two candidates cannot be attributed to their gem5 hardware
knobs, which do not reconfigure the physical native-inference server. Repeat
measurements are required before treating the latency difference as stable.

## Measurement boundaries

Native latency is measured on the real llama.cpp host. gem5 evaluates a packed
Q4 14/2/64 attention proxy for comparative hardware design-space exploration;
it does not simulate the full Qwen model or establish absolute full-model
latency.

Energy is estimated dynamic access energy for two L1 instruction caches, two
L1 data caches, and one shared L2 cache. It excludes processor-core logic,
DRAM, interconnect, TLBs, static/leakage energy, and native Qwen energy.

Quality is exact option-text accuracy over the 250-question team-authored,
OpenStax-aligned assessment. It is not a general factual-correctness or
open-ended tutoring metric.

## Claim boundary

This study supports claims about best observed candidates and the Pareto
frontier under two ten-candidate budgets. It does not prove a global optimum or
statistical superiority. The preferred candidate must be described as
`preferred best-observed candidate`, and repeated matched campaigns are needed
for stronger method-level conclusions.

## Files

- `campaign-summary.json`: compact campaign, integrity, objective-winner, and
  selection summary.
- `candidates.csv` and `candidates.json`: all 20 candidates, knobs, metrics,
  status, provenance labels, and frontier membership.
- `combined-pareto.csv` and `combined-pareto.json`: the independently computed
  seven-candidate combined frontier.
- `objective-winners.csv` and `objective-winners.json`: the four best observed
  objective values and their candidates.
- `SHA256SUMS`: SHA-256 digests for every curated evidence file in this
  directory except the checksum file itself.

The source analysis archive had SHA-256
`4cc8ce85892d94b2984fc6335115053895f16c798cf01aab2646ec3b72c3d078`.
Its six internal data-file checksums passed before publication.
