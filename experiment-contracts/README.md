# CHIA Experiment Contracts v0.2

A clean contract-oriented layout for the CHIA offline AI Tutor project.

## Why this replaces the current mixed layout

The previous repository structure split related schemas across `config-schema/` and `compute-policy-v0.2/`, and mixed examples, docs, runtime policy, and result records. This package groups each contract with its own schema, example/config, and documentation.

## Contract map

- `ai-tutor-config/` — application-level AI Tutor configuration.
- `attention-experiments/` — concrete gem5 attention experiments plus the CHIA design-space contract.
- `compute-policy/` — real execution/back-end/parallelism/Gemini guardrails.
- `run-record/` — evidence from an actual run.
- `docs/` — cross-contract architecture and migration notes.
- `scripts/validate_all.py` — validates all shipped YAML files and important semantic rules.

## Data flow

```text
AI Tutor config
      |
      v
Tutor -> attention mapping (to be validated)
      |
      v
Attention design space ----> CHIA proposes candidate
                                |
                                v
                        Attention experiment
                                |
                       compute policy gate
                                |
                                v
                           CHIA / Ray / gem5
                                |
                                v
                            Run record
```

## Validation

Windows:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python scripts\validate_all.py
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/validate_all.py
```

## Important rule

JSON-schema validity means the document is structurally valid. It does **not** prove that a future/planned knob is already implemented in the kernel or mapped correctly to gem5.
