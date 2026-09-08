# CHIA AI Tutor experiment contract — v0.1

This is the project-owned v0.1 configuration contract for the offline AI Tutor experiment. It uses JSON Schema Draft 2020-12 and serializes the version as `schema_version: "0.1.0"`. It is not an upstream CHIA configuration format, a `cluster.yaml` replacement, or a validated gem5/BOOM configuration.

The package is ready for a teammate to copy into a GitHub repository. It contains the schema, an annotated example, a local validator, pinned direct dependencies, and contract tests. No experiment runner or simulator adapter is implemented here.

## Validate the example

Use Python 3.10 or later. From this package directory:

```sh
python -m pip install -r requirements.txt
python validate_config.py example-experiment.yaml
python -m unittest discover -s tests -v
```

Expected validation output:

```text
VALID: example-experiment.yaml (schema 0.1.0; structural validation only)
```

The validator finds the schema beside its own script, so it also works from another directory when passed full paths. It accepts YAML or `.json` records, checks the schema itself, reports errors by field path, and rejects duplicate keys, non-string object keys, non-JSON values, and non-finite numbers. Use plain YAML mappings; YAML merge keys are unsupported. Exit codes: `0` valid, `1` schema violation, `2` file/parse/schema-loading error. Validation does not fetch references, download models, execute CHIA, or contact a simulator.

## Inputs, outputs, and ownership

| Section | Role | Owner and meaning |
| --- | --- | --- |
| `schema_version` | Contract discriminator | All components must accept the exact version. |
| `metadata` | Identity / evidence reference | Orchestrator assigns a unique run ID; writes the artifact manifest reference when available. |
| `workload` | Fixed INPUT conditions | Evaluation owner pins questions, corpus, protocol, sample count, and seed. Hold fixed within a comparison. |
| `software` | INPUT knobs | Software runner selects the model and precision, retrieval count, and generation limit. Batch size is secondary. |
| `hardware` | Provisional INPUT knobs | Simulator adapter maps requested target architecture to verified implementation parameters. |
| `metrics` | OUTPUT measurements | Evaluators write measured or explicitly documented estimated values. Never optimization inputs or invented predictions. |
| `status` | OUTPUT lifecycle | Orchestrator initializes `planned`, then records `running`, `completed`, or `failed`. |

Each record represents one candidate and one repetition. A sweep generator produces multiple records; lists/ranges of candidates do not belong inside an individual record. Freeze inputs once execution starts, assign a new ID to retries/repetitions, and retain the submitted record with the results.

## Knob definitions and v0.1 bounds

These bounds are **project search limits**, chosen to keep early experiments small. They are not published hardware limits or a claim that every combination is supported.

| Knob | Accepted values | Interpretation |
| --- | --- | --- |
| `software.model` | Nonblank identifier/path | Prefer one fixed base model initially; manifest pins immutable model/tokenizer and weight artifacts. |
| `software.quantization` | `fp16`, `bf16`, `int8`, `int4` | Dominant weight format; recipe and runtime still need pinning. FP16/BF16 are floating-point precision options under this shared field name. |
| `software.retrieval_top_k` | Integer 1–16 | Requested chunks per question; retrieval is enabled in v0.1. |
| `software.max_new_tokens` | Integer 1–1024 | Maximum output tokens per answer, excluding prompt tokens. |
| `software.batch_size` | Optional integer 1–8 | **Secondary**; runner uses 1 when omitted. Validator does not insert defaults. Keep 1 initially. |
| `hardware.l1_cache_kb` | 16, 32, 64, 128 | KiB of L1 **data** cache per target core; instruction cache fixed. |
| `hardware.l2_cache_kb` | 128, 256, 512, 1024, 2048, 4096 | KiB of **total shared** L2 capacity. |
| `hardware.cores` | Integer 1–8 | Target CPU cores, independent of Ray workers and runtime thread count. |
| `hardware.issue_width` | Integer 1–8 | Requested aggregate issue capacity in micro-operations per core per cycle; not achieved IPC. |

The cache `_kb` names preserve the discussion's spelling but mean **KiB = 1024 bytes**, not kilobits or decimal kB. Cache topology and issue-width semantics above are explicit design assumptions, pending implementation verification. Unknown fields are rejected at every object level, so misspelled or speculative knobs cannot silently enter an experiment.

## Output metric contract

All five keys must exist. Use `null` before measurement or when unavailable; never substitute zero. Zero is a measured value. Numeric metrics are finite and nonnegative; quality additionally has an upper bound of 1. Resource metrics have no invented upper ceilings.

| Metric | Definition / unit | Pareto direction |
| --- | --- | --- |
| `answer_quality` | Mean protocol-defined rubric score in [0,1]; dimensionless, not inherently accuracy | Maximize |
| `latency_ms` | Mean per-question arrival-to-complete-answer time, including queue/batch wait, retrieval, and generation; ms | Minimize |
| `energy_joules` | Target-system energy over the evaluation interval / completed questions; J/question | Minimize |
| `memory_mb` | Peak total resident memory attributable to the target tutor workload during evaluation; decimal MB = 1,000,000 bytes | Minimize |
| `throughput_qps` | Completed questions / evaluation interval in seconds; questions/s | Maximize |

The evaluation interval runs from the first measured question's arrival to the last measured completion. Startup and protocol-defined warmup are excluded. Pin arrival schedule, batch policy, decoding, timing boundaries, and memory/energy accounting in the protocol. Record completion counts and per-question measurements in the manifest's referenced evidence. Do not silently score only successful answers in a failed run.

Target simulated time differs from host simulator execution time. Host simulator memory is not target tutor memory. Kernel-only or proxy simulations must retain their own scope in separate evidence; do not fill end-to-end tutor fields from a proxy unless an explicit, validated estimation method supports that conversion. Energy stays null until a documented measurement or calibrated model is available. Do not mix physical measurements and simulation estimates within a Pareto comparison without an explicit comparability study.

`planned` requires all metrics null. `running` and `failed` may retain partial results; `failed` requires a message. `completed` requires at least one numeric metric and a non-null artifact manifest reference. It can retain null metrics, with reasons documented in the message/manifest. Completion does not certify correctness or Pareto eligibility. The validator does not inspect evidence files or enforce historical state transitions.

## Why this is the integration contract

```text
Candidate generator / CHIA orchestration
                  |
           validated record
             /         \
 software runner     hardware adapter
       |                   |
 answers + traces    target simulation evidence
             \         /
          evaluation + provenance
                  |
          metrics + run status
                  |
        comparison / Pareto analysis
```

These are intended integration boundaries, not implemented CHIA nodes in this package. Shared names, units, version checks, and ownership let teammates develop the runner, simulator adapter, evaluator, and analysis independently. Each stage consumes the same frozen inputs and attaches evidence under the same experiment ID. The deterministic validator catches structural mistakes before expensive work; adapter checks establish actual execution support.

Pareto analysis must first select completed runs with comparable workload/protocol and measurement scope. For the selected objective set, exclude records with a null objective; report exclusions rather than imputing zero. Candidate A dominates B when A is no worse on every selected objective and strictly better on at least one. Declare quality thresholds and objective subsets before the sweep. Keep per-repetition records and examine variability before claiming one design is better.

## Current assumptions and unknowns

- **Discussion-grounded scope:** small offline tutor; one model initially; quantization, retrieval top-k, and output length as primary software variables; batching secondary. Cache sizes, cores, and issue width are requested hardware variables. Earlier example performance numbers were illustrative and are not copied as results.
- **v0.1 design decisions:** numeric bounds, L1-data/per-core and shared-L2 interpretation, normalized quality rubric, metric aggregation, workload reference fields, and lifecycle rules are established here for integration. They are not claimed to come from CHIA documentation.
- **Exact gem5/BOOM support is UNKNOWN.** No selected simulator checkout, commit, CPU configuration, or adapter was supplied/verified for this package. The simulator owner must pin the exact implementation and map each field to code/config locations. Verify L1 instruction/data separation, L2 topology, per-queue issue widths, legal core counts, cache geometry, and coupled constraints. Reject unsupported combinations; never silently coerce them. A gem5 CPU model must not be assumed equivalent to a BOOM configuration.
- **Runtime support is UNKNOWN.** Pin the model, tokenizer, quantization recipe, inference runtime/kernels, target ISA, thread policy, and context/truncation policy. INT4/INT8 labels alone do not prove target support or speedup. Verify that the simulated workload actually reflects each software knob.
- **Evaluation assets and energy method are UNKNOWN.** The example uses explicit placeholder IDs; it passes structural validation but is not executable. Replace them with real versioned assets and an agreed protocol before running. Schema validation does not resolve these references.
- **Reproducibility is a runner responsibility.** The artifact manifest must record code/CHIA/runtime/simulator revisions, resolved artifact hashes, fixed hardware baseline (including frequency/memory settings), requested-to-applied knob mapping, protocol and dataset/corpus revisions, measurement sources/coverage, raw result paths, completion counts, and reasons for unavailable metrics. Its detailed schema is deferred until the runner and simulator are chosen.
- **Deferred knobs:** frequency, memory bandwidth/capacity, cache associativity, chunk size, embedding-model selection, pruning, distillation, and dynamic batching are not v0.1 search fields. Relevant fixed values belong in the protocol/manifest. Add new knobs only after adapter verification and a schema version change.

## Next integration milestone

Choose and pin the runtime and simulator; write a one-candidate adapter that verifies requested versus applied settings; run a fixed tiny question set; retain answers and raw measurements; populate only defensible metrics. Compare against the same fixed baseline before expanding the sweep. This schema package is a reusable project handoff suitable for saving into Project Sources.

## Sources and version policy

Project intent: [Build CHIA Learning Roadmap](chatgpt-conversation://6a96a4d8-6d1c-83eb-9c8c-0ab39102c650), reviewed September 8, 2026; access may be limited to project members. The decisions needed to use this package are restated above.

Schema dialect: [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12). Validator API: [python-jsonschema validation documentation](https://python-jsonschema.readthedocs.io/en/stable/validate/).

Keep released schemas immutable. Change `schema_version` and publish a corresponding schema when accepted fields, bounds, units, or meanings change; record migration guidance. Correcting prose without changing the contract may be documented as an editorial correction. No repository URL or upstream approval is implied.
