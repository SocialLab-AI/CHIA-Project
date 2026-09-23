# Project Brief — Edge AI Tutor Co-Design

Read this alongside the README. This is *what* we're building and *why*; the README is *how we work*.

## The problem

Schools with limited internet or hardware budget can't rely on cloud LLM tutors. We're building an **offline AI tutoring system** that runs on low-cost CPU hardware — the kind of machine actually found in those classrooms.

This is a full-stack **Domain-Specific Architecture co-design** entry: we don't just tune software *or* hardware, we optimize both together.

## What the system is

An offline, inference-only AI Tutor. The executable baseline is Qwen2.5 0.5B Instruct with Q5_K_M weights, served on native CPU through llama.cpp.

The native software measurement and simulated attention-kernel proxy are separate executions. See the [architecture](docs/ARCHITECTURE.md), [experiment methodology](docs/EXPERIMENT_METHODOLOGY.md), and [validated results](docs/RESULTS.md).

## The loop

Using CHIA, we run one optimization loop that repeats: **propose a joint SW+HW configuration → run the evaluations → measure metrics → adjust → repeat.** The agent reasons over results and picks the next configuration to try.

### What we optimize

**Software knobs**

- Sampling temperature
- Maximum generated tokens

The model artifact, Q5_K_M quantization, CPU threads and sequential request topology are fixed for this campaign.

**Hardware knobs (gem5)**

- CPU model and frequency
- L1D and L2 cache sizes and associativities
- Instruction issue width

The simulated hardware uses a fixed two-core configuration and two kernel threads.

### How we evaluate each candidate

Each candidate produces four separate minimization objectives:

- **Native latency** — measured through Qwen inference on CPU.
- **Proxy simulated time** — measured by gem5 for the attention kernel.
- **Estimated cache dynamic energy** — estimated by Accelergy + McPAT from gem5 cache counters.
- **Answer quality loss** — one minus required-concept coverage on three attributed OpenStax conceptual questions. References remain evaluator-only.

Native Tutor measurements and the gem5 attention proxy remain separate objective domains. The current proxy is an abstraction and does not claim to predict complete Qwen latency.

## Why gem5 runs a proxy, not the model

Full model inference inside gem5 would take too long. We simulate a **Qwen-shaped packed-Q4 attention proxy** with 14 query heads, 2 KV heads, and head dimension 64 on CPU hardware. It supports comparative hardware exploration and context-scaling analysis, not absolute full-model latency prediction.

## What we're producing

A **budget-bounded Pareto frontier** over the four objectives above. The completed one-candidate smoke validates the integrated path; it does not establish optimizer superiority. The deliverables are:

- the open-source optimization code (the CHIA loop),
- the evaluation harnesses (native quality + gem5 metrics),
- the experiment/dataset configurations.

## Where each of us fits

- **admatieh** — the CHIA loop: nodes, edges, the agent that proposes configs.
- **yahyafl** — gem5: the proxy model, the HW knobs, latency/memory/energy extraction (incl. Accelergy/McPAT).
- **sara-alsayyah** — the tutor workload: inference runtime and OpenStax required-concept coverage evaluation.
- **Lynn** — architecture, the config schema, integration of the measurement paths, submission.

Nobody's boxed in — every issue has a reviewer from another stream, and the point is that all of us understand the whole loop.
