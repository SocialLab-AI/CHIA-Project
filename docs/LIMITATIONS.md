# Limitations

The 14/2/64 attention proxy represents Qwen attention geometry for comparative hardware design-space exploration. Proxy validation supports context-scaling trend fidelity, not absolute full-model latency equivalence. gem5 does not simulate the entire Qwen model.

Native latency includes local llama.cpp HTTP round trips for three OpenStax questions and depends on the server and host. Required-concept coverage can miss correct paraphrases and does not establish factual correctness. Word-boundary matching prevents obvious substring false positives such as `earth` matching `earthquake`.

OpenStax currently states that College Physics 2e is CC BY-NC-SA 4.0 and separately restricts use in or ingestion into generative-AI offerings without permission. The final runtime therefore requires `OPENSTAX_LLM_PERMISSION_CONFIRMED=1`. Set it only when the campaign operator has confirmed the required permission; until then, this is a smoke blocker.

Energy estimates dynamic access energy for two L1I caches, two L1D caches, and one shared L2 cache using aggregate gem5 hit/miss counters. Aggregate lookups are modeled as reads because current counters do not distinguish reads and writes. The estimate excludes processor-core logic, DRAM, interconnect, TLBs, static/leakage energy, and native Qwen energy.

The three-candidate setting is a pilot, not a final burst size. Gemini pricing is an estimate from the reviewed compute policy. Results support best-observed and budget-bounded Pareto claims only.
