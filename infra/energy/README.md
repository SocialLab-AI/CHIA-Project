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

## Production flow

```text
validated candidate
  -> gem5 14/2/64 attention proxy
  -> isolated stats.txt and resolved config.json
  -> deterministic cache mapping
  -> architecture.yaml + action_counts.yaml
  -> Accelergy 0.3 + McPAT 1.3
  -> energy_estimation.yaml
  -> five-component and identity verification
  -> energy-enriched hardware result
  -> controller-owned CHIA run record
```

gem5 and Accelergy execute sequentially inside one CHIA hardware task selected
by the `gem5` Ray resource. The complete sequence shares the hardware deadline;
the configured energy timeout is a smaller optional cap. A timeout forcibly
removes the named Docker container and creates a failed record rather than a
completed result.

The reported value covers dynamic access energy for two L1 instruction caches,
two L1 data caches, and one shared L2 cache. Aggregate gem5 lookups are modeled
as reads because the retained counters do not distinguish reads from writes.
It excludes processor-core logic, DRAM, interconnect, TLBs, static/leakage
energy, and native Qwen energy.

Every completed estimate records the container digest, pinned tool versions and
commits, execution duration, energy scope, and SHA-256 hashes of the mapping,
architecture, action counts, gem5 statistics, and energy result.

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
