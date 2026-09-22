# Objectives

Every feasible candidate emits four independent minimization objectives:

1. `native_latency_ms`: observed llama.cpp request latency aggregated across the 250 assessment questions.
2. `proxy_simulated_seconds`: gem5 simulated execution time for the 14/2/64 proxy.
3. `estimated_cache_dynamic_energy_uj`: Accelergy estimate for modeled L1I, L1D, and shared L2 dynamic access energy.
4. `answer_quality_loss`: `1 - answer_quality` from exact option-text accuracy.

No weighted sum is used. A candidate is Pareto dominated only when another candidate in the same profile, context, and dataset group is no worse on every objective and better on at least one.

Quality is the fraction of responses that exactly match the correct unlabeled option after Unicode, case, and whitespace normalization. Extra explanations, labels, partial strings, and ambiguous responses receive no credit. Per-subject accuracy and position diagnostics accompany the aggregate. This measures assessment accuracy, not complete educational quality. Energy is not total Qwen energy; it excludes core logic, DRAM, interconnect, TLBs, leakage, and native inference energy.
