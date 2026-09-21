# Results and evidence

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

## Backend labels and deployment provenance

The final validated deployment ran on GCP. The corresponding validated release is
identified by the annotated tag `micro-2026-chia-validated`, which points to
`bcbf685c47ea73ed29184991d795735a3d8c67cc`.

Recorded configuration labels must be distinguished from the deployment provider:

- The committed [smoke summary](experiments/evidence/final-burst-smoke-20260921/summary.json)
  records `execution_profile.backend: local` for
  `run-e9ba2424838246afad8f6183810e8cd1` at source commit
  `45b21950b9cdc59c0e388b98bb661550dce97632`.
- `experiment-contracts/campaigns/final-burst.yaml` at that source commit used
  `backend: contabo`. Commit `e24cb3446fc4bc4c40f93aa6cdd9c7605416107b`
  changed the canonical campaign to `backend: gcp` and documented that a
  completed GCP smoke had carried the incorrect `contabo` label. That note
  does not identify a run ID; the raw server records are not committed, so it
  cannot establish that label for the specific run summarized above.
- The current canonical campaign uses `backend: gcp`. The README's
  single-server integration overlay explicitly changes its label to `local`.

Historical evidence remains unchanged. Neither the older `local` summary label
nor the former `contabo` campaign label changes the recorded GCP deployment.

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
