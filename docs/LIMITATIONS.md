# Limitations

The 14/2/64 attention proxy represents Qwen attention geometry for comparative hardware design-space exploration. Proxy validation supports context-scaling trend fidelity, not absolute full-model latency equivalence. gem5 does not simulate the entire Qwen model.

Native latency includes 250 separate local llama.cpp HTTP round trips and depends on the server and host. Exact option-text accuracy is stricter and more reproducible than the previous concept matcher, but it measures performance on a team-authored multiple-choice assessment rather than open-ended tutoring quality.

The questions use original team-authored wording aligned to OpenStax topic scope; OpenStax did not author the exact assessment. The runtime requires `TEAM_ASSESSMENT_LLM_PERMISSION_CONFIRMED=1` so the operator explicitly attests that the team-provided material is approved for model evaluation.

Energy estimates dynamic access energy for two L1I caches, two L1D caches, and one shared L2 cache using aggregate gem5 hit/miss counters. Aggregate lookups are modeled as reads because current counters do not distinguish reads and writes. The estimate excludes processor-core logic, DRAM, interconnect, TLBs, static/leakage energy, and native Qwen energy.

The completed ten-candidate Gemini campaign is still a pilot until it is paired
with the equal-budget seeded-random campaign. One rejected Gemini duplicate was
replaced by a deterministic fallback, so the ten evaluated candidates comprise
nine Gemini proposals and one fallback. Gemini pricing is an estimate from the
reviewed compute policy. Results support best-observed and budget-bounded Pareto
claims only.
