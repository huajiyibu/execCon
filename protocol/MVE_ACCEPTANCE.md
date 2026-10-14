# Minimal Validation Element Acceptance Gates

A run is valid only if every gate passes.

1. Identity: task, cohort, harness, resource mode, spec, pool, code, model, prompts and tool schemas are fingerprinted.
2. Isolation: every candidate owns a fresh session and sandbox; no writable state is shared.
3. Provenance: every artifact has exactly one producer, path, byte length and SHA-256.
4. Freeze: every condition references the same immutable bundle hash.
5. Treatment purity: E0 and E1 non-evidence projections are byte-identical.
6. Budget: the convergence program, prompt, model settings and output protocol are equal.
7. Decision: fallback and unresolved states are explicit and auditable.
8. Delivery: output is empty before write; post-write bytes and hashes match the decision.
9. Evaluation: official Score and Pass fields are retained; hidden grading fields never enter convergence input.
10. Logging: every failure has a causal record and an explicit invalidation scope.

Any failure invalidates the whole MVE. Scores from an invalid MVE are diagnostic only.
