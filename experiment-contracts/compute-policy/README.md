# Compute Policy Contract

## Purpose

Controls **real execution**, not simulated hardware.

It answers:
- Which backends may run a tier?
- How many jobs may run in parallel?
- May real Gemini API calls be used?
- May organizer burst compute be used?

## Why the YAML is intentionally small

The machine-readable policy should contain only rules software needs to enforce. Longer reasoning and promotion criteria belong in documentation.

## Tier intent

- `dev` — local/Contabo smoke tests and debugging; real Gemini allowed in small controlled use.
- `integration` — small real end-to-end CHIA/Gemini/gem5 tests; stronger dev compute allowed.
- `pilot` — meaningful scale used to measure cost, runtime, failure rate, and validate methodology.
- `final` — frozen campaign on organizer burst resources.

Core principle: **nothing scales until the smaller stage works**.
