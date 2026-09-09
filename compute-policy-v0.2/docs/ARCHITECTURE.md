# Architecture: Progressive Compute Validation + Split Schemas

## 1. Thesis

The team should not equate **local** with **free** or **cloud** with **final**. The correct rule is:

> **Nothing scales until a smaller version passes.**

Real Gemini calls are allowed during development, and a stronger development VM is allowed when the team server is a bottleneck. What is forbidden is scaling an unvalidated loop into many paid API calls or large organizer burst runs.

## 2. Separation of concerns

```text
experiment.yaml                 compute-policy.yaml
"What do we test?"              "Where/how may we run it?"
        |                               |
        +---------------+---------------+
                        v
                  CHIA controller
                        |
              deterministic admission
                        |
                        v
                 attention kernel
                        |
                        v
                       gem5
                        |
                        v
                 run-record.yaml
              "What actually happened?"
```

### Experiment schema
Contains scientific variables only:

- workload dimensions: sequence length, head dimension, heads, batch, dtype;
- software/kernel knobs: kernel variant, optional tiling, threads;
- simulated hardware knobs: L1/L2, cores, issue width.

### Compute policy schema
Contains governance only:

- allowed real backends per tier;
- parallelism limits;
- Gemini allowed/not allowed;
- Gemini budget envelopes;
- whether organizer burst is allowed;
- promotion gates.

### Run-record schema
Contains observed facts:

- actual tier/backend/worker;
- correctness and gem5 metrics;
- Gemini usage and estimated cost;
- Git/tool/prompt provenance;
- completion/failure state.

## 3. Tier policy

### Tier 0 — dev
Purpose: component correctness and smoke testing.

- Prefer local/Contabo.
- One job at a time by default.
- 1-5 tiny runs as guidance.
- Real Gemini calls allowed when needed.
- Cache/replay Gemini responses during repeated parser/orchestration debugging.
- No organizer burst.

Exit only after: schema validation, kernel correctness, gem5 stats, CHIA round-trip, persistent result record, and at least one real Gemini integration check.

### Tier 1 — integration
Purpose: prove the real end-to-end loop and knob propagation.

- Local/Contabo or a small development cloud VM.
- Small parallelism (default 2).
- Roughly 5-12 candidates as guidance.
- Real Gemini enabled.
- Deterministic validation must sit between Gemini and execution.

Agentic boundary:

```text
Gemini proposes -> schema/range/duplicate validator -> execute or reject
```

Gemini must not choose the compute tier or bypass spending controls.

### Tier 2 — pilot
Purpose: validate methodology and measure the economics of the final campaign.

- Contabo or development cloud.
- Moderate parallelism (default 4).
- Roughly 20-50 candidates, but actual size comes from measured runtime.
- Freeze workload definition, knob ranges, correctness tolerance, metrics, baseline, and search budget before starting.
- Measure median/percentile gem5 wall time, failures, configs/hour, Gemini calls/tokens/cost per candidate.

The pilot must make final cost and runtime predictable.

### Tier 3 — final
Purpose: generate evidence for final claims.

- Organizer burst backend.
- Frozen Git commit, schema, policy, prompt version, seeds, and tool versions.
- Final candidate count derived from pilot evidence and available organizer capacity.
- Run baseline and CHIA strategy under a fair evaluation budget.
- Do not hot-edit workers mid-campaign. A real code bug stops the campaign and returns to an appropriate validation tier.

## 4. Why this architecture is optimal for this hackathon

1. **Fast debugging:** small failures are discovered before scale multiplies them.
2. **Budget control:** Gemini spend is metered from the beginning without banning realistic API testing.
3. **Compute flexibility:** the team can use a stronger development VM if Contabo is too slow.
4. **Scientific reproducibility:** final data comes from frozen code and recorded provenance.
5. **Clean CHIA responsibility:** CHIA orchestrates candidate generation, validation, scheduling, execution, and feedback; the policy remains deterministic governance.
6. **Maintainability:** scientific config, operational policy, and observed results can evolve independently.
7. **Fair evaluation:** baseline and CHIA search can be compared under the same simulation/evaluation budget.

## 5. What is still UNKNOWN and must be verified

- Exact attention-kernel implementation and its exposed software knobs.
- Which tiling controls (`tile_q`, `tile_k`, `tile_v`) are real and useful.
- Exact gem5 mapping for L1, L2, cores, and especially issue width.
- Correctness tolerance for the selected datatype/implementation.
- gem5 simulation wall time for representative attention shapes.
- Organizer burst capacity and operational constraints.
- Exact Gemini model used by the CHIA agent and actual pricing/credit behavior.

Do not freeze a knob merely because it appears in a schema. A knob belongs in the final contract only when we can **change it, validate it, run it, and measure its effect**.
