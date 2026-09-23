# Experiment methodology

The study asks whether Gemini-guided CHIA search finds better observed configurations or Pareto candidates more efficiently than seeded random search under the same budget. It does not assume either method wins.

Both methods use the same model artifact and SHA check, 250-question team-authored OpenStax-aligned assessment, prompt, software and hardware spaces, 14/2/64 proxy, cache-energy estimator, exact option-text evaluator, candidate budget, timeouts, stopping rules, resources, repetitions, persistence, and four objectives. Random sampling uses a recorded seed and samples without replacement. Gemini receives the legal active spaces and prior results; deterministic code validates every response. Invalid, malformed, rejected, duplicate, retry, and fallback outcomes remain in the proposal ledger. Token counts come from SDK usage metadata. A request failure without usage metadata is recorded as unmetered rather than falsely reported as zero. Cost is an estimate using reviewed policy rates, not verified billing.

Compare best observed feasible candidates, Pareto frontiers, objective values, evaluations needed to reach frontier quality, invalid and duplicate proposals, wall time, infrastructure failures, and Gemini token/cost overhead. Report only “best observed candidate(s)” and “Pareto frontier under the campaign budget.” A global-optimum claim requires exhaustive evaluation.

Stage 1 is one deterministic 250-question smoke candidate. Stage 2 is a three-candidate pilot per method. Use measured smoke and pilot wall time, disk use, failures, artifact size, and Gemini usage to set the approved burst budget.
