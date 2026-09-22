# Running

The root [README](../README.md) is the authoritative single-server installation
and command guide. The release sequence is deliberately staged:

1. Install the repository, reviewed model, llama.cpp service, gem5 image, and
   energy image on one server.
2. Start one Ray node with `control`, `llama_cpp`, and `gem5` resources.
3. Run contract validation, validate-only, non-scheduling tests, and
   `git diff --check`.
4. Confirm the team-assessment permission attestation, then run the fail-closed release
   preflight. It verifies native runtime identity and performs a bounded
   five-cache Accelergy + McPAT round trip without running gem5 or Gemini.
5. Run one deterministic smoke candidate and verify its manifest, completed run
   record, four objectives, and energy provenance.
6. Run the three-candidate random pilot, then the equal-budget Gemini pilot only
   after API use is approved.
7. Derive any larger burst budget from observed pilot time, failures, disk use,
   artifact size, and Gemini usage.

The hardware task owns gem5 and Accelergy on the same `gem5` worker. Its total
timeout covers image preflight, compilation, simulation, mapping, energy
execution, and verification. Existing campaign directories cause a fail-closed
error so prior evidence cannot be overwritten.
