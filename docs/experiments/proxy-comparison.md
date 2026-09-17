# Repeated proxy-profile comparison

This is the continuation experiment for Issue #60. It compares two corrected one-layer attention profiles under the same gem5 hardware configuration, context lengths and repetition count:

| Profile | Query heads | KV heads | Head dimension | Kernel iterations per trial |
|---|---:|---:|---:|---:|
| `original-corrected` | 4 | 2 | 32 | 1 |
| `qwen-shaped` | 14 | 2 | 64 | 1 |

Both profiles use grouped-query KV mapping and generic two-thread head dispatch. The production full loop remains fixed to its reviewed baseline. Only `scripts/run_proxy_comparison.py` enables the calibration validation path.

The native llama-bench evidence reports F16 keys and F16 values. The proxy uses packed Q4 KV data. This experiment therefore evaluates structural shape, context scaling and Q4 approximation behavior; it does not claim runtime KV-format equivalence.

## Prepare the local configuration

Copy the example to an ignored local file:

```bash
cp experiment-contracts/testing/proxy-comparison.server.example.yaml \
  experiment-contracts/testing/proxy-comparison.server.local.yaml
```

Set a unique `experiment_id`. Point `native_evidence_directory` to a completed fidelity directory containing `model-profile.json` and `native-context-sweep.json`. Review the container image, timeout and existing absolute tolerance. Do not loosen the tolerance before seeing the normalized-error results.

## Execute

Validate the protocol and native evidence before connecting to Ray:

```bash
python -m scripts.run_proxy_comparison \
  --config experiment-contracts/testing/proxy-comparison.server.local.yaml \
  --validate-only
```

This confirms the saved model digest, contexts, native KV-cache metadata, and
the number of planned gem5 jobs. It does not submit work. Then run from the
repository root with the CHIA cluster active:

```bash
python -m scripts.run_proxy_comparison \
  --config experiment-contracts/testing/proxy-comparison.server.local.yaml
```

The default protocol runs 30 sequential simulations: two profiles × five contexts × three trials. Profiles are interleaved deterministically. Every completed trial is written to `checkpoint.json`; rerunning the same command resumes matching work. If code, shape, tolerance or image settings change, choose a new experiment ID instead of mixing protocols.

## Outputs

```text
results/proxy-comparison/<experiment-id>/
├── checkpoint.json
├── proxy-comparison.json
├── REPORT.md
├── normalized-context-trends-original-corrected.svg
├── normalized-context-trends-qwen-shaped.svg
└── SHA256SUMS.json
```

The report compares context-rank correlation, normalized-trend mean absolute percentage error, tolerance violations, repeated simulated time and worst observed normalized errors. Absolute gem5 time is not a winner criterion because the profiles intentionally perform different amounts of work.

## Decision rule

Prefer the Qwen-shaped profile only if its numerical approximation remains controlled and its normalized context trend is at least as defensible as the corrected original. Keep the Issue #60 decision open until the generated report and checksums are reviewed.
