# Design space

The fixed native model is **Qwen2.5-0.5B-Instruct Q5_K_M**, served by llama.cpp on CPU. The dataset is the three-question, source-located OpenStax College Physics 2e Chapter 4 conceptual set in `data/questions/questions.json`; evaluator references are isolated in `data/references/openstax.json`. College Physics 2e is licensed CC BY-NC-SA 4.0, and the campaign is a noncommercial research evaluation.

The production proxy is one packed-Q4 grouped-query attention layer with **14 query heads, 2 KV heads, and head dimension 64**. Context length is an evaluation axis, not an active knob within a comparison group.

The canonical software space is `experiment-contracts/design-spaces/software.yaml`. Active knobs are temperature and maximum output tokens. Model, quantization, backend, CPU threads, and batch size are fixed.

The canonical hardware space is `experiment-contracts/design-spaces/hardware.yaml`. Active knobs are CPU model, frequency, issue width, L1D size and associativity, and L2 size and associativity. Constraints include two cores, SE mode, fixed cache latencies, fixed DDR3 memory, two kernel threads, and `issue_width=1` for `RiscvTimingSimpleCPU`.

The corrected 4/2/32 kernel is retained only as calibration evidence. Production candidate validation rejects it.
