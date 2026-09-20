# Results and evidence

No final integrated smoke or campaign result is committed. The production baseline therefore contains null metrics. Existing proxy-comparison evidence under `docs/experiments/evidence/qwen-proxy-comparison-20260918-01/` supports context-scaling trend comparison and selection of the Qwen-shaped proxy; it is not evidence of full-model latency equivalence.

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

Provenance records Git state, source hashes, Python and package versions, model SHA expectation, dataset hash, design-space hash, campaign hash, and runtime/container identities when observable. Missing evidence stays null or absent.
