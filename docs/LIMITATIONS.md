# Limitations

The 14/2/64 attention proxy represents Qwen attention geometry for comparative hardware design-space exploration. Proxy validation supports context-scaling trend fidelity, not absolute full-model latency equivalence. gem5 does not simulate the entire Qwen model.

Native latency includes 250 separate local llama.cpp HTTP round trips and depends on the server and host. Exact option-text accuracy is stricter and more reproducible than the previous concept matcher, but it measures performance on a team-authored multiple-choice assessment rather than open-ended tutoring quality.

The questions use original team-authored wording aligned to OpenStax topic scope; OpenStax did not author the exact assessment. The runtime requires `TEAM_ASSESSMENT_LLM_PERMISSION_CONFIRMED=1` so the operator explicitly attests that the team-provided material is approved for model evaluation.

Energy estimates dynamic access energy for two L1I caches, two L1D caches, and one shared L2 cache using aggregate gem5 hit/miss counters. Aggregate lookups are modeled as reads because current counters do not distinguish reads and writes. The estimate excludes processor-core logic, DRAM, interconnect, TLBs, static/leakage energy, and native Qwen energy.

The first completed ten-candidate Gemini campaign was a pilot. It was followed
by matched and confirmatory Gemini-versus-random comparisons, but each contains
only one campaign per method and ten candidates per arm. The results support
best-observed and budget-bounded Pareto claims, not a global optimum or
statistical method-level superiority. Gemini pricing is an estimate from the
reviewed compute policy.

The preferred candidate and the energy-winning candidate use identical native
software knobs. gem5 hardware knobs do not reconfigure the physical server that
runs native Qwen inference, so their native-latency difference may be ordinary
runtime variation. Repeated measurements of finalists are required before the
observed latency ordering can be treated as stable.
