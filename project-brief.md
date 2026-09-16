# Project Brief — Edge AI Tutor Co-Design

Read this alongside the README. This is *what* we're building and *why*; the README is *how we work*.

## The problem

Schools with limited internet or hardware budget can't rely on cloud LLM tutors. We're building an **offline AI tutoring system** that runs on low-cost CPU hardware — the kind of machine actually found in those classrooms.

This is a full-stack **Domain-Specific Architecture co-design** entry: we don't just tune software *or* hardware, we optimize both together.

## What the system is

An offline, inference-only AI Tutor. The executable baseline is Qwen2.5 0.5B Instruct with Q5_K_M weights, served on native CPU through llama.cpp.

The native software measurement and simulated attention-kernel proxy are separate executions. See [current implementation](docs/FULL_LOOP.md) and [status](docs/IMPLEMENTATION_STATUS.md) for evidence and remaining gates.

## The loop

Using CHIA, we run one optimization loop that repeats: **propose a joint SW+HW configuration → run the evaluations → measure metrics → adjust → repeat.** The agent reasons over results and picks the next configuration to try.

### What we optimize

**Software knobs**
- Sampling temperature
- Maximum generated tokens

The model artifact, Q5_K_M quantization, CPU threads and sequential request topology are fixed for this campaign.

**Hardware knobs (gem5)**
- L1 and L2 cache sizes
- Instruction issue width
- CPU core count

### How we evaluate each candidate

Two separate measurement paths that the loop fuses into one objective:

- **Answer quality** — measured *natively* on three attributed OpenStax conceptual questions with deterministic required-concept rubrics. References remain evaluator-only.
- **Hardware metrics** — measured in **gem5**: simulated time, instructions, IPC, cache miss rates and memory traffic.

Native Tutor measurements and the gem5 attention proxy remain separate objective domains. The current proxy is an abstraction and does not claim to predict complete Qwen latency.

## Why gem5 runs a proxy, not the model

Full model inference inside gem5 would take far too long — cycle-level simulation is orders of magnitude slower than real execution. So we profile **representative GEMM (matrix-multiply) kernels and SimPoint regions** that stand in for the tutor's compute, instead of running whole inferences. We stay on **CPU edge hardware** throughout, to match the real classroom deployment target.

## What we're producing

An **optimized Pareto frontier** mapping answer quality against latency, energy, and memory. Concretely, the deliverables are:

- the open-source optimization code (the CHIA loop),
- the evaluation harnesses (native quality + gem5 metrics),
- the experiment/dataset configurations.

## Where each of us fits

- **admatieh** — the CHIA loop: nodes, edges, the agent that proposes configs.
- **yahyafl** — gem5: the proxy model, the HW knobs, latency/memory/energy extraction (incl. Accelergy/McPAT).
- **sara-alsayyah** — the tutor workload: inference runtime, OpenStax QA eval, the reviewer-model scorer.
- **Lynn** — architecture, the config schema, how the two metric paths fuse, integration, submission.

Nobody's boxed in — every issue has a reviewer from another stream, and the point is that all of us understand the whole loop.
