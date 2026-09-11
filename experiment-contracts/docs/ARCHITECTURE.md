# Architecture

## Four contracts, four responsibilities

| Contract | Question answered |
|---|---|
| AI Tutor config | What application configuration are we evaluating? |
| Attention experiment/design space | What proxy workload and simulated architecture are we evaluating? |
| Compute policy | Where and at what scale may the real job execute? |
| Run record | What actually happened and what evidence was produced? |

## Separation that must remain explicit

`hardware.*` inside an attention experiment describes the **simulated target architecture** in gem5.

`execution.backend` inside a run record and the compute policy describes the **real host/backend** running CHIA/gem5.

Those are different layers and must never be conflated.

## CHIA control

CHIA may propose values only from the active design space. Deterministic validation checks legality before execution.

Gemini may propose candidates, but it must not:
- authorize a higher compute tier,
- enable organizer burst,
- invent unsupported knob values,
- bypass schema/semantic validation.
