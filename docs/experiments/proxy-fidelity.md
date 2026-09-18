# Qwen–gem5 proxy fidelity experiment

This is the execution protocol for [Issue #60](https://github.com/SocialLab-AI/CHIA-Project/issues/60). It tests whether the current gem5 attention kernel follows useful workload trends from the exact Qwen2.5 Q5 GGUF used by the Tutor. It does not simulate the complete model.

## Current status

| Item | Status | Evidence or remaining work |
|---|---|---|
| Exact GGUF architecture extraction | IMPLEMENTED | `src/tutor/model_profile.py` reads the selected file's GGUF header and verifies its SHA-256. |
| Native Qwen context sweep | IMPLEMENTED | `src/tutor/benchmark.py` runs CPU-only `llama-bench` at 128, 256, 512, 1024 and 2048 prompt tokens. |
| gem5 proxy context sweep | IMPLEMENTED | The Issue #60 runner dispatches the existing candidate-driven gem5 adapter for the same five contexts. |
| gem5 hardware sensitivity | IMPLEMENTED | The runner evaluates the baseline plus reviewed sensitivity cases at 512 tokens. |
| Normalization, Spearman rho, plot and report | IMPLEMENTED | Analysis writes machine-readable JSON, an SVG plot and a Markdown report. |
| Distributed execution evidence | IMPLEMENTED | Native profiling and the original proxy sweep completed using a control host plus a resource-labelled gem5 worker. |
| Durable evidence archival | PARTIAL | This branch records the reported measurements and decisions. The generated JSON/report/checksum bundle remains deployment-local and must be copied to the final review location before closing Issue #60. |
| Equivalent native hardware rank comparison | RISK | The native host cannot change its physical cache sizes, associativity, issue width or memory controller to match the gem5 candidates. |
| Qwen-shaped proxy remapping | PARTIAL | Grouped-query mapping, generic head dispatch, normalized-error output and the repeated distributed comparison are complete. Both profiles are preserved; F16/Q4 alignment, numerical acceptance and final team selection remain. |

The measured outcome and developer handoff are recorded in [Proxy calibration decision and handoff](proxy-calibration-handoff.md). That document is the current source for the experiment result, discovered defects, interpretation and remaining acceptance gates.

The next execution protocol is the [repeated proxy-profile comparison](proxy-comparison.md).

## What is measured

**FACT:** The native sweep measures Qwen prompt processing with the exact GGUF, CPU-only llama.cpp build, fixed thread count and repeated samples. `llama-bench` latency excludes model loading, tokenization and sampling. GNU `time` memory and CPU measurements, and optional Linux `perf` counters, cover the whole benchmark process.

**FACT:** The gem5 workload executes one representative attention kernel with packed-Q4 KV-cache data, a floating-point reference and deterministic correctness checks. It excludes projections, MLP blocks, embeddings, tokenization, sampling, all-layer repetition and the llama.cpp runtime.

**FACT:** The normal full loop fails immediately when the reviewed Q4 error tolerance is exceeded. This calibration sweep instead retains every finite raw error, marks each violation, and continues so a failed approximation becomes evidence rather than a missing experiment. Non-finite output and workload failures still stop execution.

**INTERPRETATION:** Native prompt processing and the proxy's single-query attention are not identical operations. Their normalized context trends are useful evidence, but a positive correlation does not prove cycle-accurate full-model fidelity.

**UNKNOWN:** Hardware-configuration rank preservation cannot be calculated on the present cluster because there is no native Qwen platform with gem5-equivalent configurable caches and issue width. The report records this as unavailable instead of inventing a correlation.

## Operator procedure

Run from the repository root on the control host. Keep the local operator config uncommitted; `*.local.yaml` is ignored. The paths below are examples and must be replaced with local installation paths.

```bash
source /absolute/path/to/chia/.venv/bin/activate
python -m pip install 'gguf==0.19.0'

cmake --build \
  /absolute/path/to/llama.cpp/build-chia \
  --target llama-bench \
  -j 4

cp \
  experiment-contracts/testing/proxy-fidelity.server.example.yaml \
  experiment-contracts/testing/proxy-fidelity.server.local.yaml
```

Set these two values in `proxy-fidelity.server.local.yaml`:

```yaml
native:
  model_path: /absolute/path/to/qwen2.5-0.5b-instruct-q5_k_m.gguf
  llama_bench: /absolute/path/to/llama.cpp/build-chia/bin/llama-bench
```

The committed SHA-256 belongs to the exact reviewed server model. The profile phase will stop if the file differs.

Execute the phases separately so a long gem5 run can be diagnosed or resumed without repeating native measurements:

```bash
python -m scripts.run_proxy_fidelity \
  --config experiment-contracts/testing/proxy-fidelity.server.local.yaml \
  --phase profile

python -m scripts.run_proxy_fidelity \
  --config experiment-contracts/testing/proxy-fidelity.server.local.yaml \
  --phase native

python -m scripts.run_proxy_fidelity \
  --config experiment-contracts/testing/proxy-fidelity.server.local.yaml \
  --phase hardware

python -m scripts.run_proxy_fidelity \
  --config experiment-contracts/testing/proxy-fidelity.server.local.yaml \
  --phase analyze
```

The hardware phase runs five context cases plus the configured sensitivity cases. It can take substantially longer than the native phase. CHIA sends every gem5 case to the worker carrying the `gem5: 1` resource label; it does not retry failed simulations automatically.

## Evidence bundle

The default output directory is:

```text
results/proxy-fidelity/qwen-gem5-proxy-fidelity-v1/
├── model-profile.json
├── native-context-sweep.json
├── gem5-proxy-sweep.json
├── analysis.json
├── normalized-context-trends.svg
├── REPORT.md
└── SHA256SUMS.json
```

`REPORT.md` contains the real-model versus current-proxy dimension table, explicit scope, normalized context trends, Spearman context correlation, gem5 sensitivity ordering, limitation statement and the evidence-based conclusion:

- `A_CALIBRATED_PROXY` is intentionally unavailable under the present protocol because equivalent native hardware rankings cannot be observed.
- `B_PARTIAL_PROXY` means the measured context ordering agrees, while the proxy remains limited to an attention kernel.
- `C_PROXY_NEEDS_REVISION` means the context ordering is nonpositive or at least one finite numerical result exceeds the reviewed tolerance.

Do not change the proxy dimensions until the first evidence bundle has been copied and reviewed. That preserves proof of the original mismatch requested in Issue #60.
