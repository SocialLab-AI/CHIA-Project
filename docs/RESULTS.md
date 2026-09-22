# Results and evidence

## Dataset transition

The smoke and ten-candidate Gemini pilot documented below were produced at
their recorded source commits with the earlier three-question concept-coverage
dataset. The current release contract replaces that dataset with the
250-question team-authored OpenStax-aligned assessment and exact option-text
accuracy. Historical quality values remain valid for their recorded commits,
but they must not be compared directly with results from the new evaluator.

## Verified one-candidate integration smoke

The first complete final-profile smoke passed on 2026-09-21 at Git commit
`45b21950b9cdc59c0e388b98bb661550dce97632`. The run used the no-sudo
single-server integration profile, one deterministic candidate, no Gemini or
random proposer calls, and one measurement repetition per OpenStax question.
It is evidence that the integrated execution path works. It is not a
repeatability study, an optimizer comparison, or evidence of a global optimum.

| Field | Observed value |
| --- | --- |
| Campaign | `final-burst-smoke` |
| Run | `run-e9ba2424838246afad8f6183810e8cd1` |
| Candidate | `b900e503b88c7c1447c07cf4e2ddf4fbd816f988761b0a95f52b317e7c716aff` |
| Campaign state | `completed` |
| Wall time | 895.992291153 seconds |
| Native latency objective | 6862.006723999 ms |
| Proxy simulated-time objective | 0.0854 seconds |
| Cache dynamic-energy objective | 9136.5186591748 microjoules |
| Quality | 0.6666666667 |
| Quality-loss objective | 0.3333333333 |
| Proxy geometry | 14 query heads / 2 KV heads / 64 head dimension |
| Proxy correctness | `PASS` |
| Gemini requests | 0 |
| Pareto candidates | 1 |
| Stop reason | `iteration_limit` |

The hardware simulation executed 197,462,665 instructions and 85,400,011,000
ticks, representing 0.0854 simulated seconds. gem5 used 600.38 host seconds.
Proxy validation reported maximum absolute error `0.013470888` and mean squared
error `0.000014581`, both within the configured tolerances.

The measured energy is dynamic cache access energy for two L1I caches, two L1D
caches, and one shared L2 cache. It excludes processor-core logic, DRAM,
interconnect, TLBs, static/leakage energy, and native Qwen energy. Energy
execution took 288.763794016 seconds. The completed record contained all five
required components and Accelergy, McPAT, mapping, architecture, action-count,
and result provenance hashes.

Every generated file listed in `MANIFEST.sha256` passed `sha256sum --check`.
The compact machine-readable evidence is committed at
`docs/experiments/evidence/final-burst-smoke-20260921/summary.json`. Raw native,
gem5, and energy artifacts remain in the campaign result directory on the
execution server and are excluded from Git because they include generated
binaries and machine-specific simulator output.

Existing proxy-comparison evidence under
`docs/experiments/evidence/qwen-proxy-comparison-20260918-01/` supports
context-scaling trend comparison and selection of the Qwen-shaped proxy; it is
not evidence of full-model latency equivalence.

## Ten-candidate Gemini pilot

The `final-burst-gemini` pilot completed on 2026-09-21 at Git commit
`adc85e51d9684921830e6b6bb1cbcdaeeb2c3ebc`. All ten candidate evaluations
completed. Nine candidates came from accepted Gemini proposals; a repeated
proposal on the eighth Gemini request was rejected and replaced with one
deterministic fallback candidate.

| Field | Observed value |
| --- | --- |
| Campaign state | `completed` |
| Stop reason | `iteration_limit` |
| Campaign wall time | 9468.836 seconds |
| Completed candidates | 10 |
| Observed Pareto candidates | 6 |
| Gemini requests | 10 |
| Accepted proposals | 9 |
| Rejected duplicates | 1 |
| Malformed responses | 0 |
| Gemini tokens | 32,937 |
| Estimated Gemini cost | USD 0.00993925 |

The lowest observed native latency was 3382.129 ms. The lowest proxy simulated
time was 0.019288 seconds. The lowest estimated cache dynamic energy was
9136.519 microjoules, produced by the deterministic fallback. The highest
observed required-concept coverage score was 0.6667. No single candidate
minimized every objective.

All candidate records passed completed-record validation, candidate IDs were
unique, comparison groups agreed, and the stored Pareto frontier matched an
independent recomputation. The execution-server manifest also passed in full.
The reviewed evidence and complete candidate table are under
`docs/experiments/evidence/final-burst-gemini-20260921/`.

This is a Gemini-guided pilot rather than the final optimizer comparison. It
does not establish that Gemini outperforms random search. The matched
250-question comparison documented below supersedes it for method comparison.

## Matched Gemini-versus-random comparison

The first matched comparison completed on 2026-09-22. Seeded random and
Gemini-guided search each evaluated ten candidates with the 250-question exact
option-text evaluator. All 20 records completed and passed the repository's
completed-record validator. Both execution-server manifests passed, and each
stored per-campaign Pareto frontier matched an independent recomputation.

| Field | Seeded random | Gemini-guided |
| --- | ---: | ---: |
| Completed candidates | 10 | 10 |
| Per-campaign Pareto candidates | 6 | 6 |
| Combined-frontier contribution | 6 | 6 |
| Best native latency | 1258.766 ms | **1251.860 ms** |
| Best proxy simulated time | 0.019325 s | **0.019288 s** |
| Best cache dynamic energy | **6429.489 uJ** | 8370.200 uJ |
| Best exact option-text accuracy | **46.0%** | 45.2% |
| Campaign wall time | 9835.876 s | 9173.489 s |
| Proposal failures | 0 | 0 |

There is no single overall winner under this ten-candidate budget. Each method
contributed six candidates to the combined 12-candidate frontier. Gemini found
the best observed native-latency and proxy-time candidates; random found the
best observed quality and cache-energy candidates. Random dominated four
Gemini candidates, while Gemini dominated two random candidates, but this
secondary coverage result does not erase the equal frontier contribution or
the split objective winners.

The model, dataset hashes, design space, evaluator, proxy, energy estimator,
runtime versions, budgets, stopping rules, and deterministic evaluation source
hashes match. The campaign Git commits differ because the later Gemini run used
the corrected four-objective proposer prompt in
`src/orchestration/gemini_api.py`; that method-specific proposer is the only
recorded runtime source-hash difference. The evidence is therefore useful for
this observed comparison, with that provenance qualification stated.

The reviewed evidence, all 20 candidate rows, individual and combined
frontiers, proposal accounting, provenance comparison, and integrity hashes
are under
`docs/experiments/evidence/final-burst-250q-gemini-vs-random-20260922/`.
This single 10-versus-10 study does not establish statistical superiority or a
global optimum. Multiple matched repetitions are required for a stronger
method-level claim.

## Campaign evidence layout

Each campaign creates:

```text
results/<campaign-id>/
  campaign.yaml
  environment.json
  provenance.json
  summary.json
  events.jsonl
  pareto.json
  runs/run-*.json
  native/run-*.json
  gem5/...
  energy/run-*.json
  gemini/usage.json and proposals.jsonl, or random/metadata.json
  MANIFEST.sha256
```

Provenance records Git state, source hashes, Python and package versions, model
SHA expectation, dataset hash, design-space hash, campaign hash, and
runtime/container identities when observable. Missing evidence stays null or
absent.
