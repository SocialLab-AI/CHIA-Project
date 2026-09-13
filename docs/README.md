# Project documentation

Start here for the offline AI Tutor and CHIA hardware/software co-design project.

| Read | Purpose |
|---|---|
| [Overview](overview.md) | Project scope, current status, and remaining work |
| [Architecture](architecture.md) | Components, interfaces, and execution flow |
| [Configuration](configuration.md) | Where contracts live and how to edit them |
| [Running](running.md) | Local validation and hardware execution prerequisites |
| [Knob mapping](knob-mapping.md) | Configuration fields, planned bindings, and metrics |
| [Glossary](glossary.md) | Terms used in this project |
| [Experiment evidence](experiments/README.md) | Current Q4 report and historical FP32 evidence |

The [contract directory](../experiment-contracts/README.md) owns configuration values and validation rules. Link to those inputs instead of maintaining another baseline in documentation.

The [mapping manifest](knob-mapping.manifest.json) is machine-readable documentation used by validation; it is not an executable knob registry.

Keep current behavior separate from planned integration. Historical results describe the run that produced them; do not rewrite their measurements to match a later baseline. Update the relevant guide when code or configuration paths change.
