# chia-hackathon

Our entry for the **A³ workshop hackathon @ MICRO 2026 (Athens)**, built on the CHIA framework.

**What we're building:** an agentic HW/SW co-design loop for an **edge AI tutor**. A CHIA loop drives an optimizer over both software knobs (the tutor workload) and hardware knobs (a gem5 model), evaluates each candidate, and iterates toward configurations that trade off answer quality against on-device compute cost.

- CHIA: https://github.com/ucb-bar/chia · https://chialoops.ai · paper: https://arxiv.org/abs/2606.27350
- gem5: https://www.gem5.org

## Team & ownership

Everyone owns a primary area but nobody works in isolation — every issue has a reviewer from another stream.

| Person | GitHub | Owns |
|---|---|---|
| Lynn (lead) | `lynn511` | Architecture, integration decisions, evaluation, submission |
| Intern 1 | `admatieh` | CHIA framework + the agentic optimization loop |
| Intern 2 | `yahyafl` | gem5 / hardware simulation + infra |
| Intern 3 | `sara-alsayyah` | AI tutor workload + evaluation + experiment tracking |

## Two decisions that shape everything (Phase 1)

1. **gem5 runs a proxy, not the real model.** Full LLM inference inside gem5 is infeasible in a hackathon window — cycle-level simulation is far too slow. We simulate a *representative proxy* (kernels / a small benchmark / sampled regions) that stands in for the tutor's compute profile. Deciding this proxy is a P0 blocker; the gem5 and tutor work depend on it.
2. **The config schema is the contract.** One shared schema describes every HW knob, every SW knob, and every metric. All three streams build against it from day one — this is what stops us shipping three good components that don't connect. Defined in Phase 1, before the foundations.

## Compute rule

We have three compute sources. Use them in this order, and **nothing touches paid or burst compute until it passes locally.**

- **Local** — all dev, debugging, and small experiments.
- **$300 GCP credit** — Gemini API metering only. Not for compute we can run locally.
- **Organizer burst (temporary unlimited)** — final validated runs only. Fire the pre-written run list; don't improvise inside the window.

Submissions are scored on cost, compute efficiency, and runtime, so **per-run cost tracking is a graded deliverable**, not hygiene. Log spend, tokens, and runtime as you go (see the cost-tracking issue).

## The board

Issues live in the GitHub Project. Columns: **Backlog → Ready → In Progress → Review → Integration-Test → Done**. `Blocked` is a label, not a column.

Labels:
- **Phase:** `phase:1` … `phase:4`, `cross-cutting`
- **Area:** `CHIA` `GEM5` `AI-TUTOR` `EVALUATION` `INTEGRATION` `GCP` `RESEARCH` `DOCUMENTATION`
- **Priority:** `P0` `P1`
- **Compute:** `compute:local` `compute:gcp` `compute:burst`

Owner and reviewer for each task are in the issue body. Start with `phase:1` `P0` items.

## Ground rules

1. Every issue has an **owner** and a **reviewer from another stream**.
2. No PR merges without explaining **what** was done, **why**, and **how it was validated**.
3. Every major component ships a short README so someone else can reproduce it.
4. Regular integration sessions — each person demos **actual running code**, not slides.
5. Rotate reviewers so Intern 1 learns gem5, Intern 2 learns CHIA, and Intern 3 sees the whole pipeline.
6. No branches that sit isolated for days. Integrate small increments continuously.

The biggest risk on a project like this is three solid pieces that never connect. Integration tickets are first-class, not end-of-hackathon cleanup.

## Repository layout

```text
experiment-contracts/   # canonical schemas, design space, configs, and run records
gem5/                   # executable attention proxy, gem5 configuration, and metrics
src/                    # stable software/hardware/orchestration adapter boundaries
scripts/                # CLI boundaries
data/                   # tutor questions and evaluation references
prompts/                # tutor prompts
infra/                  # CHIA and infrastructure configuration
results/                # generated experiment outputs
docs/                   # decisions, architecture, and experiment evidence

experiment-contracts/ is the configuration source of truth. The executable
hardware path lives under gem5/. The src/ package defines the modular
integration boundaries; some tutor and orchestration components intentionally
remain skeletons while their implementation is finalized.
