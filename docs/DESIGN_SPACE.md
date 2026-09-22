# Design space

The fixed native model is **Qwen2.5-0.5B-Instruct Q5_K_M**, served by llama.cpp on CPU. The canonical dataset is the 250-question, five-subject team assessment in `data/questions/questions.json`; evaluator answers are isolated in `data/references/answer_key.json`. The questions use original team-authored wording aligned to the topic scope of five OpenStax textbooks. They must not be described as text authored by OpenStax.

Each question presents four answer texts without A/B/C/D labels. Option order is deterministically permuted with a recorded seed, and correct positions are balanced 63/63/62/62 to prevent the original answer-position imbalance from becoming a shortcut.

The production proxy is one packed-Q4 grouped-query attention layer with **14 query heads, 2 KV heads, and head dimension 64**. Context length is an evaluation axis, not an active knob within a comparison group.

The canonical software space is `experiment-contracts/design-spaces/software.yaml`. Active knobs are temperature and maximum output tokens. Model, quantization, backend, CPU threads, and batch size are fixed.

The canonical hardware space is `experiment-contracts/design-spaces/hardware.yaml`. Active knobs are CPU model, frequency, issue width, L1D size and associativity, and L2 size and associativity. Constraints include two cores, SE mode, fixed cache latencies, fixed DDR3 memory, two kernel threads, and `issue_width=1` for `RiscvTimingSimpleCPU`.

The corrected 4/2/32 kernel is retained only as calibration evidence. Production candidate validation rejects it.
