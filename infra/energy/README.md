# CHIA gem5 Energy Toolchain

This directory defines the reproducible Accelergy and McPAT environment used for CHIA gem5 energy estimation.

## Pinned tools

- McPAT 1.3
- Accelergy 0.3
- Accelergy McPAT plug-in 0.1

The exact Git commits are stored in `versions.env`.

Accelergy 0.3 is required because the current McPAT plug-in uses the older Accelergy plug-in interface. Accelergy 0.4 introduced an incompatible interface.

The image runs through `chia-accelergy`, which stages the installed estimator
plug-ins and Accelergy configuration in a per-container temporary directory.
This is required because Accelergy 0.3 and the McPAT plug-in write generated XML
and cache files beside the configured plug-in. The production runner still uses
the host worker's unprivileged UID/GID.

## Build

From the repository root:

```bash
cd infra/energy

set -a
source versions.env
set +a

docker build \
  --build-arg "ACCELERGY_REF=$ACCELERGY_REF" \
  --build-arg "PLUGIN_REF=$PLUGIN_REF" \
  --build-arg "MCPAT_REF=$MCPAT_REF" \
  --tag chia-energy-tools:0.3 \
  .
```
