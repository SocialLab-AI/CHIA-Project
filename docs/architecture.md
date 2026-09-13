# Architecture

CHIA will coordinate native tutor evaluation and a simulated attention proxy using validated experiment configurations. The executable hardware path exists; the full integrated loop is planned.

```text
CHIA / candidate selection (planned integration)
                     |
         configuration and policy validation
                     |
         +-----------+------------+
         |                        |
 native tutor adapter       hardware adapter
      (planned)                 (planned)
         |                        |
 llama.cpp + retrieval      gem5/run_attention_experiment.py
      (planned)                   |
         |                  attention_kv.c + attention-riscv.py
 held-out evaluation              |
         |                       gem5
 application metrics              |
         |                  extract_metrics.py
         +------------+-----------+
                      |
          evidence records and scoring
             (integration pending)
```

## Implemented hardware path

[`run_attention_experiment.py`](../gem5/run_attention_experiment.py) loads the attention configuration, checks supported settings, builds the C workload through Docker, runs gem5, and writes extracted metrics. [`attention-riscv.py`](../gem5/attention-riscv.py) configures the simulated hardware. [`extract_metrics.py`](../gem5/extract_metrics.py) translates simulator statistics into hardware metrics.

The runner output is an attention experiment with metrics; it is not automatically a complete run record containing all execution, usage and provenance fields. The [run-record contract](../experiment-contracts/run-records/run-record.schema.json) describes that separate evidence requirement.

## Project interfaces

[`run_experiment(config)`](../src/orchestration/experiment.py) passes the full configuration to both runners. [`run_hardware(config)`](../src/hardware/runner.py) and [`run_tutor(config)`](../src/tutor/runner.py) currently raise `NotImplementedError`. The hardware adapter does not yet delegate to the existing gem5 pipeline. The CHIA entrypoint is also planned.

The [knob mapping](knob-mapping.md) records intended bindings. A planned binding is not proof that a candidate service or optimizer has been implemented.

## Boundaries

- Native tutor CPU threads and simulated proxy threads describe different executions.
- Model-weight Q4_K_M and proxy KV-cache Q4 are separate representations.
- Application latency, simulated time, and simulation host runtime are distinct measurements.
- Retrieval content must remain separate from held-out OpenStax reference answers.
- Gemini may propose candidates; deterministic validation and compute-policy checks must govern execution. A schema-valid configuration does not prove runtime capability.

See [configuration](configuration.md) for contracts and [running](running.md) for supported entrypoints.
