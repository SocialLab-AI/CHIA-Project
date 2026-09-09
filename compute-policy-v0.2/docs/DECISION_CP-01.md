# Project Decision CP-01 — Progressive Compute Validation

**Status:** Proposed for team adoption  
**Scope:** CHIA attention-kernel design-space exploration

## Decision

Use four execution tiers: `dev`, `integration`, `pilot`, `final`.

The governing rule is **nothing scales until a smaller version passes**. Real Gemini API calls are allowed in development/integration when necessary to validate the actual agent loop. A stronger development cloud VM is allowed when team-owned compute is an engineering bottleneck. Organizer burst is reserved for the final validated campaign.

## Boundary

- Gemini/agent may propose scientific candidates.
- Deterministic code validates schema, ranges, duplicates, correctness prerequisites, and compute-policy admission.
- Gemini may not promote tiers, choose organizer burst, or override budget limits.

## Rationale

This balances deadline pressure, realistic testing, budget control, reproducibility, and the need to generate defensible final evidence.

## Review trigger

Revisit CP-01 if pilot measurements show that the proposed tier limits or backend choices make the final campaign infeasible.
