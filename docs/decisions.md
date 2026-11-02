# Physical design decisions

1. PostgreSQL is authoritative; MongoDB and Neo4j are replayable projections. All local service ports bind to 127.0.0.1.
2. The conceptual ER is preserved. Physical operational tables add manifests, validation, features, outbox and benchmark metadata.
3. Assertion versions represent contiguous local observation episodes, not an assertion that our revision number equals an official SCV revision. Disappearance closes an episode; return creates another.
4. Release IDs are assigned in accepted chronological order. Visibility is `[first_release_id,last_release_id)`. Evaluation date is a reported event-date attribute, not a complete valid-time interval or a substitute for observation time.
5. Gene participation is restricted to one unambiguous selected gene. Assembly is GRCh38 and germline classifications are read separately from somatic columns.
6. Conflict flag is derived by a rule view. Event classes are retrieved by endpoint joins, not independently stored copies.
7. Realized labels are model-independent. `prediction_outcome` corrects the extra nonkey dependency introduced by repeating outcomes in a model-specific prediction row. The result view exposes the earlier documented field name.
8. The initial target is a reconstructed aggregate endpoint group difference. Official comparisons are persisted explicitly. Small-cohort metrics and agreement are not medical or generalization claims.
9. Each fitted run has its own model identity, source-cutoff hash, feature list and implementation hash. Future outcomes are joined only for evaluation; training labels must mature by the origin.
10. UI: React + TypeScript + Vite, with the reference design retained. The former static implementation is removed. Kerykeion is the only product brand; ClinVar remains the public data source.
11. Corrections and changed contracts require a separate frozen dataset revision. Source archives/filtered extracts and model artifacts are ignored by Git; their manifest hashes are persisted.
12. Current source schema lacks a numeric submitter ID. The fallback is a local name hash; an identity change on an existing SCV fails explicitly and needs review. No unverified lab-identity merge is performed.
