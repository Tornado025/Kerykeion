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

## Submitter name changes in historical TSV archives

March 2025 retains SCV accessions while changing some organisation names (for
example, 3billion to 3billion, Medical Genetics). Because the TSV provides names
rather than stable organisation IDs, the importer records `submitter_alias`
entries supported by unchanged SCV and variant ownership. An alias must resolve
to one existing organisation; contradictory evidence, changed variant ownership
or changed provider IDs remain errors. New SCVs with the same renamed name ID
use that canonical organisation too. Original submitted names stay in raw evidence;
name changes start a new evidence episode. The organisation table retains its
first observed display name. This is a documented identity heuristic, not an
assertion that the source provided an official organisation identifier.

## Final three-gene experiment protocol

The delivered cohort remains the user's selected BRCA1, BRCA2 and TP53 scope,
across January 2025–November 2026. Both 1- and 3-release endpoint targets are run
with fixed logistic regression / boosted-tree parameters, seed 42, and preprocessing
fit only to eligible past training rows. Training origin u is allowed only when
u+h <= the prediction origin. Early partial-history rows are explicit via
history_length; primary paired reporting begins after six releases of history.
There is no future-label hyperparameter search or automatic winner selection.

Fitted artifacts have SHA-256 checksums and source hashes. Run completion commits
independently, so a stopped job preserves completed runs. Repeating the exact code,
cutoff and configuration refreshes metrics without refitting or duplicating scores.
The API lists the latest version of each method/input/origin/horizon combination;
older run IDs remain queryable through their reproducibility endpoint.

Predictions beyond the final archive have unknown outcomes. Model-independent
outcomes and archived feature documents remain separate. The prediction-input UI
shows observed values, not unsupported causal explanations or invented SHAP values.
Scores remain uncalibrated; the reliability plot measures that limitation.

Sensitivity checks remove feature groups, shuffle historical input blocks within
gene at the test origin, and exclude each gene from training in turn. They use
fixed settings at the last evaluable h1 origin and do not choose production models.
Paired uncertainty uses a circular moving-block bootstrap over release origins
(block 3, 2,000 draws, seed 42). This is a limited-panel diagnostic, not evidence
of clinical validity or robust generalisation to other genes.

Evidence revisions follow the importer contract's classification, review,
evaluation-date and identity fields; unversioned prose-only changes are not used
as model inputs. The source mismatch ledger retains every official-versus-calculated
disagreement and a secondary result subset checks agreeing endpoint pairs.

## Laptop-friendly projections

MongoDB stores each variant/origin/input-set feature vector once and a context
document per model run. A prediction joins those two identities; its score remains
in PostgreSQL. Older prototype per-prediction context documents may remain as
legacy records but are not required by the new read path. The API verifies the
projected feature hash before displaying MongoDB context and can fall back to the
authoritative relational snapshot while delivery is pending. Run CPU-intensive
jobs sequentially under the Compose CPU/memory limits in the README.
