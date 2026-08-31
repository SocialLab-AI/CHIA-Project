# Project Brief — Edge AI Tutor Co-Design

Read this alongside the README. This is *what* we're building and *why*; the README is *how we work*.

## The problem

Schools with limited internet or hardware budget can't rely on cloud LLM tutors. We're building an **offline AI tutoring system** that runs on low-cost CPU hardware — the kind of machine actually found in those classrooms.

This is a full-stack **Domain-Specific Architecture co-design** entry: we don't just tune software *or* hardware, we optimize both together.

## What the system is

A small **retrieval-augmented question-answering (RAG) pipeline**:

- A **sub-1B language model** (candidate: Qwen2.5-0.5B) generates answers.
- An **embedding model** retrieves relevant reference text to ground those answers.

Both run on a simulated CPU edge target — no GPU, no cloud at inference time.

## The loop

Using CHIA, we run one optimization loop that repeats: **propose a joint SW+HW configuration → run the evaluations → measure metrics → adjust → repeat.** The agent reasons over results and picks the next configuration to try.

### What we optimize

**Software knobs**
- Model quantization level
- Retrieval top-k (how many passages we pull)
- Batch size

**Hardware knobs (gem5)**
- L1 and L2 cache sizes
- Instruction issue width
- CPU core count

### How we evaluate each candidate

Two separate measurement paths that the loop fuses into one objective:

- **Answer quality** — measured *natively* per software config. Questions come from a subset of the **OpenStax QA dataset**; a reference answer is the ground truth; an automated **reviewer model** scores our system's responses against it.
- **Hardware metrics** — measured in **gem5**: latency, memory utilization, and energy. Energy comes from **Accelergy + McPAT** on top of the gem5 run.

Quantization is the knob that couples the two: it changes both answer quality (measured natively) and the compute profile fed to gem5.

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
- **sara-alsayyah** — the tutor workload: RAG pipeline, OpenStax QA eval, the reviewer-model scorer.
- **Lynn** — architecture, the config schema, how the two metric paths fuse, integration, submission.

Nobody's boxed in — every issue has a reviewer from another stream, and the point is that all of us understand the whole loop.
