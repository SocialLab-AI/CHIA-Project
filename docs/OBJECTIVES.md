# Objectives

Every feasible candidate emits four independent minimization objectives:

1. `native_latency_ms`: observed llama.cpp request latency aggregated across OpenStax questions.
2. `proxy_simulated_seconds`: gem5 simulated execution time for the 14/2/64 proxy.
3. `estimated_cache_dynamic_energy_uj`: Accelergy estimate for modeled L1I, L1D, and shared L2 dynamic access energy.
4. `answer_quality_loss`: `1 - answer_quality` from required-concept coverage.

No weighted sum is used. A candidate is Pareto dominated only when another candidate in the same profile, context, and dataset group is no worse on every objective and better on at least one.

Quality measures normalized whole-word or phrase coverage of curated required concepts. It is not a factual-correctness or semantic-equivalence score. Energy is not total Qwen energy; it excludes core logic, DRAM, interconnect, TLBs, leakage, and native inference energy.
