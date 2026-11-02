# ClinVar Time Machine — implementation plan

This is a proposed build plan based on the project documents. Acceptance interfaces and effort estimates are planning recommendations.

## 1. Build order, scope and definition of the finished system

1. Implement the project in this order: source feasibility → normalized PostgreSQL core → three-release history and drift slice → full backfill → as-of features and labels → baselines and evaluation → MongoDB/Neo4j projections → API and demo → replay, performance and final report. This is an implementation plan, not a claim that those components already exist in the current workspace.

2. The first working milestone is deliberately small: BRCA1, BRCA2 and TP53, where they fit the declared scope, across three consecutive archived releases. It must already support a historical assertion query, one state per variant/release, change-event reconstruction and a safe rerun. Synthetic fixtures cover transitions that do not happen in those particular real releases.

3. The complete target is the documented approximately seventy-gene GRCh38 cohort over 12–24+ monthly releases, with a reproducible temporal benchmark, ranked audit queues, three functioning stores and a usable local demonstration. A first candidate full window is January 2025–October 2026: 22 paired monthly archives are visible in the checked NCBI listing [S1]. Validate all selected pairs before freezing the manifest.

4. Use one authoritative relational database and a single application codebase. Add the document and graph projections after the relational slice is correct; they remain required for the complete three-store deliverable. Delay the optional sequence model and optional submitter-following graph edges until the main system passes.

5. Planning estimate: approximately 140–240 focused person-hours for a careful student implementation with some familiarity with Python and SQL. At roughly 25 productive hours per week, budget six to ten weeks, with additional allowance for major source-format problems or limited hardware. This is a workload estimate, not a promise or a replacement for measuring the first milestone.

6. Completion means a fresh setup can import the frozen cohort, reconstruct histories, reproduce fold definitions and metrics, replay both projections without duplicates, serve the agreed queries and export a labelled results report. A positive temporal-model improvement is not required for honest completion.

## 2. Freeze these implementation contracts before coding the importer

1. Create docs/decisions.md and config/project.yaml. Record assembly, gene list, release window, classification channel, supported variant representations, missing-data policy, class mapping, aggregation policy, target and evaluation budgets. Put each under a version or checksum so outputs identify the exact contract used.

2. Use germline classification for the primary experiment. Do not mix germline significance, somatic clinical-impact categories and oncogenicity into one P/V/B/C/O target. Discover the actual source headers and map the chosen channel explicitly.

3. Preserve the accepted conceptual ER. For its one-selected-gene scope, retain only records with a defensible selected association; quarantine ambiguous/multigene mappings with a reason rather than silently choosing the first gene. Start with unambiguous GRCh38 SNVs and short indels; add other representations only when their identity and coordinates are handled consistently. State every final exclusion.

4. Use stable VariationID and SCV accession as source identities where available. Assign local assertion revisions independently of source revision numbers. Preserve source revision metadata separately when available. A local revision identifies a contiguous observed episode; a disappeared assertion that returns later gets a new episode even if its content repeats.

5. Order releases using an explicit chronological release_seq. Horizons and range boundaries use this sequence, not an assumption that arbitrary database IDs are consecutive calendar months. Store the actual release date separately.

6. Represent visibility with half-open integer ranges. A version visible at sequence 10 through 12 has [10,13). Close it when a complete later import establishes replacement or absence. A failed, partial or differently scoped import must never count as evidence of disappearance.

7. Primary label: group(v,t+h) differs from group(v,t); h=1 primary and h=3 secondary. Review-only changes are recorded separately. Horizon three compares endpoints, not whether any intermediate change occurred. Evaluate on rows with both endpoints present and report coverage/exclusions.

8. Freeze the rule is_conflicting = (aggregate_class == CONFLICT). Implement CLASS_CONFLICT_RULE as the small logical rule view unless a physical table is needed for coursework. Store event endpoint references and reconstruct their classes with joins.

9. Important refinement: the realized outcome depends on variant, origin, horizon and target definition, not on the model. Store it once in prediction_outcome and expose realized_label through a prediction-result view. Duplicating it in every model score introduces an additional nonkey dependency that the earlier simplified prediction checklist did not cover. Document this physical refinement rather than claim the unchanged physical row is automatically BCNF.

10. Use one isolated PostgreSQL schema or database per frozen dataset revision for the initial implementation. This preserves the documented domain keys while preventing different cohort/parser revisions from overwriting each other. Include dataset_revision in all MongoDB document keys, graph identifiers, model artifacts and export manifests; bind API queries to an explicit revision.

11. Keep imported releases immutable once published. Corrected inputs or a changed cohort/aggregation contract produce a new dataset revision and rebuilt artifacts; they must not silently rewrite the lineage behind an already evaluated model.

## 3. Application layout and recommended implementation stack

1. Use Python for parsing, import orchestration, features, evaluation and the API. Use PostgreSQL for authoritative facts; MongoDB for selected evidence, immutable feature documents and explanations; Neo4j for the temporal graph projection. Use FastAPI for read endpoints and Streamlit for the evaluator-facing local demo. These are pragmatic project choices; pin and lock tested versions instead of tracking unbounded latest releases.

2. Keep PostgreSQL at a tested major version supporting the planned range/exclusion approach; the source already reports a toy check on PostgreSQL 16. Use SQL migrations with btree_gist and an ordinary Python PostgreSQL driver. Use scikit-learn pipelines for preprocessing and logistic regression, then one boosted-tree implementation. Avoid adding Kafka, a task cluster or a separate model-tracking service for the initial local project.

3. Proposed repository: infra/compose.yaml; migrations/; config/; src/clinvar_time_machine/{ingest,temporal,aggregation,features,models,evaluation,projections,api}; ui/; tests/{unit,integration,fixtures,e2e}; artifacts/; reports/; docs/. Keep application work separate from the existing diagram-generation scripts.

4. Use a locked dependency file, .env.example, ignored real secrets, container health checks and persistent development volumes. Record the machine/CPU/RAM and software versions with benchmark results. Check actual download sizes, disk requirements and memory on the three-release slice before scaling.

5. Use migrations for schema creation, structured logs for jobs and a deterministic seed for model runs. The authoritative data path is import → validated release → states/events → as-of features → predictions/outcomes. Projection workers follow committed relational events.

6. The CLI examples in this plan are proposed acceptance interfaces, not commands already implemented: project discover; project migrate; project import --manifest ...; project build-states; project build-features; project benchmark; project project-stores; project serve. Final README commands should match the actual code.

## 4. Phase 0 — source feasibility and a frozen manifest

1. Depends on: the scope contract. Inspect two adjacent release pairs before writing a large ETL job. NCBI documents selective monthly TSV archives and more comprehensive XML downloads [S2]. The checked archive contains paired variant_summary and submission_summary files for the proposed period [S1]. Verify the actual records, not just filenames.

2. Create a field-availability matrix: source variant ID, assembly, gene identifiers, accession, submitter ID/name, selected classification, review code, evaluation date, official aggregate and any evidence fields. Inspect headers, delimiters, missing-value sentinels, multiple-value fields, duplicate keys and channel changes.

3. If a required per-assertion field is unavailable in the historical TSV, add a same-release XML adapter for that field or revise scope explicitly. Never fill a historical feature with the current live API response. Citations/evidence optional fields must not be fabricated merely to populate MongoDB.

4. Write a manifest per file with release_seq/date, URL, file role, byte count, full-stream SHA-256, schema fingerprint, parser version and local selected-extract path. Download or stream both files completely so the digest is of the whole artifact. If compressed files are removed after extraction, keep filtered reproducible extracts plus manifests.

5. Streaming limits memory, not network transfer. A gene subset still requires reading the full source stream when the archive is not server-side filtered. The listed 2026 pairs are hundreds of megabytes each [S1]; estimate total transfer and temporary storage before requesting the full window.

6. Deliverables: manifest.json, genes.csv, field_mapping.yaml, class_mapping.yaml, a small filtered extract and reports/source_feasibility.md. Exit gate: every required field has an identified historical source, both releases parse, and duplicate/source-scope ambiguities have documented handling.

## 5. Phase 1 — implement the normalized PostgreSQL core

1. Depends on: Phase 0 feasibility. Write ordered migrations, vocabulary seeds and a toy fixture before importing real archives. Keep the twelve-relation direct mapping as documentation; implement the normalized physical facts and expose familiar read views where useful.

2. Core facts: gene; release; submitter; classification_term; review_status; variant; clinical_assertion; assertion_version; variant_state; change_event; model_version; drift_prediction. The state excludes stored is_conflicting. The event excludes stored from_class/to_class. CLASS_CONFLICT_RULE is a view over class codes under the fixed flag rule.

3. Add operational support tables as needed: dataset_revision, release_artifact, import_run, validation_result, outbox_event, feature_materialization, experiment_run, fold_definition and prediction_outcome. These support lineage and execution; update the physical schema inventory instead of continuing to assert the conceptual table count.

4. assertion_version: primary key (scv_accession, local_revision); content_hash, date_evaluated, class_code, status_code, observation_span and optional source revision. Enforce EXCLUDE USING gist(scv_accession WITH =, observation_span WITH &&). PostgreSQL documents the range-plus-btree_gist pattern for this purpose [S3]. Store evaluation dates as reported event dates, not complete valid-time intervals.

5. variant_state: primary key (variant_id, release_seq) within the fixed dataset revision. Keep calculated aggregate, review stars and explicitly named counts. Put official comparison values and mismatch categories in validation_result or a separate validation snapshot. Version the aggregation policy. Event endpoint composite foreign keys must refer to both existing state rows.

6. model_version identifies method, feature definition and configuration. experiment_run records the dataset hash, code revision, seed, fold, actual training cutoff and artifact path. If one model row represents a fitted run, create a distinct row per origin/fitted artifact. Never reuse one model_id for a changing fitted object.

7. drift_prediction: unique fitted-model/variant/origin/horizon scope; score and deterministic queue rank. prediction_outcome: unique (dataset_revision, target_definition, variant_id, origin_seq, horizon), endpoint groups, outcome and maturity status. Join the two for realized_label in the API. This is the explicit correction to the prior simplified physical prediction representation.

8. Constrain nonnegative counts, valid vocabulary codes, horizon membership, source-before-destination events and score/rank domains. Add lookup indexes and GiST visibility indexes. Exit gate: migrations run on an empty database; invalid references, overlapping versions and duplicate prediction scopes fail; the normalized views reconstruct expected toy rows.

## 6. Phase 2 — resumable import and assertion episode reconstruction

1. Depends on: the schema and field mapping. Build a staging parser with explicit data types, source-row lineage and reject/quarantine reasons. Do not mutate published history while parsing an unvalidated partial file.

2. Import dimensions and identities using deterministic upserts. Canonicalize version-defining fields, compute a content hash and compare each SCV with its previous accepted observation. Same content continues the episode; changed content closes the previous episode and starts a local revision. Track absence only after a complete accepted release; returning after a gap starts a new observed episode.

3. Support unknown dates without replacing them with release dates. Preserve the original classification and review text in selected raw evidence, alongside mapped codes and mapping-version provenance. Duplicate SCV observations that disagree within one release must be quarantined or resolved by an explicit rule, not last-write-wins order.

4. Commit publication of a release, its accepted facts and outbox events atomically at an appropriately bounded unit. For large imports, staging batches may commit separately, but the release cannot become queryable as complete until all required validations pass.

5. Use stable event IDs and unique import keys. A retry of the same source must produce the same logical state, version episodes and outbox identities. Hold a release import lock to prevent concurrent imports from assigning conflicting local revisions.

6. Implement ingestion in chronological order initially. Reject an out-of-order insertion into an already sealed dataset revision unless invoking an explicit rebuild from that point. Separate source knowledge time from local ingestion timestamps.

7. Tests: unchanged assertion, changed class, changed review only, changed evaluation date, missing evaluation date, disappearance, return after a gap, duplicate row, changed source hash, parser failure mid-file and rerun after a crash. Exit gate: the three-release fixture and selected real slice give stable row hashes after a second identical import.

## 7. Phase 3 — historical queries, aggregation and change events

1. Depends on: accepted assertion history. Implement the as-of assertion query first. It filters observation_span containment before joining class/review vocabularies. A future-dated import carrying an older evaluation date must remain invisible at earlier release origins.

2. Implement aggregation as a versioned policy module/SQL query. Start from the simplified highest-review-level demonstration, but treat it as provisional until checked against official same-release aggregates in the declared germline scope. Explicitly define eligible class groups, unknown categories, selected-review counts, all-visible counts and distinct-submitter counts.

3. Build one state row per variant and release and store official-versus-calculated comparisons separately. Report mismatch rates and a confusion table by release, review level and category; inspect mismatch samples. Do not tune cohort exclusions after looking at model performance.

4. Gate before ML: require high agreement on the predeclared eligible scope, investigate every systematic mismatch, and keep a mismatch exclusion ledger. The pilot suggests 99.9% as an engineering target, not a guaranteed current result. If the reconstructed policy does not represent official change, stop or explicitly redefine/re-document the target rather than call it ClinVar aggregate drift.

5. Generate semantic group-change and review-only events separately. Bulk/batch tags follow a predeclared descriptive threshold. The primary label must come from endpoint group comparisons, not from an unqualified count of every event category.

6. Implement history(v,r), states(v,window), events(r1,r2), event_details(event_id) and gene-level drift summaries as repository queries. Recover event endpoint classes by complete-key joins. A history response should distinguish absent, unknown and present-with-known-group.

7. Deliverables: a three-release vertical slice, mismatch report and CLI query examples. Exit gate: the synthetic VUS → conflicting → pathogenic timeline is reproduced; real sample cases are traceable to source rows; the old state remains queryable after newer imports.

## 8. Phase 4 — scale the validated pipeline and establish a benchmark dataset

1. Depends on: Phase 3 passing. Expand first to a moderate window, then the frozen full gene cohort and release manifest. Record download time, parse time, accepted/rejected counts, memory and per-release state/event counts.

2. Freeze genes and filters for the complete run. Maintain an exclusion ledger for assembly ambiguity, multigene records, unsupported variant representation, missing historical fields and unmatched official aggregates. Report the final cohort, not the intended cohort alone.

3. Publish a dataset revision only when all selected paired releases are accepted. Save counts and content hashes for dimensions, version episodes, states and events. Keep downloaded filtered extracts or a reliable regeneration path; the full source need not remain on disk after verification.

4. Build drift characterization outputs: event rates with eligible denominators, direction/transition counts, review-only changes, per-gene summaries and release spikes. Denote monthly observation limits and missing endpoints.

5. Estimate training feasibility from historical training periods: number of positive transitions, label availability and how many valid origins remain after history warm-up. If the cohort provides too little signal, expand the archived window or defensible gene scope before locking the final held-out evaluation. Do not promise a model gain or silently pick only positive test releases.

6. Exit gate: one documented dataset revision can be rebuilt from manifests; each selected release has a validation report; descriptive figures reproduce; enough mature historical observations exist for at least a meaningful baseline comparison. If not, report the limitation and retain the descriptive/system outputs.

## 9. Phase 5 — leak-free features and model-independent outcomes

1. Depends on: a validated dataset revision. Build static features from the origin snapshot and temporal features from records/events observable no later than that origin. Track a lineage maximum-release and feature-definition hash for every materialization.

2. Static: group, review stars, computed conflict flag, explicitly scoped submission/submitter counts, class counts, gene and variant type. Temporal: past changes, releases since last change, arrival counts over 1/3/6 releases, new submitters, count deltas, evaluation-date ages with missingness flags, prior submitter revisions and past-only submitter change rates.

3. Features requiring six releases of history need a defined warm-up policy. Prefer an explicit warm-up period and record available-history length; do not treat unobserved early history as confirmed zero. Keep the same eligible feature rows for static and temporal model comparisons.

4. Persist immutable feature artifacts in a local columnar format for efficient repeated training, with relational materialization metadata and MongoDB documents for the planned feature-store/demo role. Store feature objects separately from future labels; never pass label fields to model input code.

5. Build prediction_outcome from states at origin and origin+h using the fixed group target. Missing either endpoint yields an ineligible/unknown outcome, not false. Keep observed outcomes distinct from pending deployed predictions. A horizon-three change-and-reversal fixture must return zero under the endpoint definition.

6. Write automated checks that fail if any feature source exceeds the origin or if a training label matures later than its training cutoff. Make all preprocessing statistics train-only. Include a backdated evaluation row arriving in a later release as an explicit negative leakage test.

7. Exit gate: repeated feature builds are identical for the same contract; adding later releases cannot change an earlier frozen feature artifact; all model candidates read the same row IDs and label definitions.

## 10. Phase 6 — baselines, fitted models and reproducible scoring

1. Depends on: features and mature labels. Implement no-change/constant-score reference, conflict ranking, recent-submission ranking and submitter-count ranking. Define deterministic tie-breaking using stable variant IDs so queue results do not depend on file order.

2. Train logistic regression first using train-fitted preprocessing, then one gradient-boosted tree model. Use the same origin folds for static and static-plus-temporal configurations. Keep feature encodings, tuning access and training rows comparable.

3. Implement a custom release-origin fold builder rather than passing panel rows blindly to TimeSeriesSplit. TimeSeriesSplit is chronological but splits indexed observations; the project additionally needs release grouping and horizon-based label maturity [S4]. At test origin T and horizon h, training origin u is eligible only if u+h <= T and the outcome is observable.

4. Use earlier chronological validation origins for tuning. Reserve final origins for untouched reporting. Record actual train-origin bounds, target horizon, dataset and feature hashes, code revision, parameters, seed and fitted artifact hash with every run.

5. At every origin, score all currently scoreable variants. Store queue rows and ranks for the complete scored population; report retrospective endpoint eligibility separately when evaluating. Define the production review budget on that scored population and report any additional evaluable-only analysis explicitly.

6. Write scores before attaching future outcomes, even in an offline backtest that has access to the full archive. Persist the release cutoff and verify it. Optional calibration must use earlier held-out data, not the final test outcomes.

7. Exit gate: a single command reproduces baseline and model predictions; rerunning an identical run does not duplicate rows; each prediction traces to one fitted artifact and as-of materialization. Delay sequence models until these runs are credible.

## 11. Phase 7 — metrics, uncertainty, ablations and result gates

1. Depends on: frozen score runs. Primary comparison: horizon-one temporal versus static on identical origins and row IDs, with PR-AUC and recall at 5%. Report PR-AUC calculation precisely: average precision is not the same estimator as trapezoidal PR area; name and fix the selected one before reporting [S5].

2. Also report precision/recall at 1% and 5%, ROC-AUC where defined, lift over uniform random, Brier score and a reliability plot for probability-producing models. Use a documented ceil(k*N) queue size with an explicit minimum-one rule for nonempty populations, and flag small-population effects.

3. For each origin, output positive count, scored count, evaluable count, excluded/missing endpoints and label prevalence. If an origin has no positives, mark undefined metrics as such; do not silently drop that origin or substitute a convenient value.

4. Report paired static–temporal differences by origin and their spread. Use a dependence-aware uncertainty method, such as paired release-block resampling with a declared block length and a variant-cluster sensitivity analysis, while acknowledging instability with few release origins. A naive independent-row bootstrap understates repeated-variant and shared-release dependence.

5. Run temporal-group ablations, history-shuffle controls that preserve appropriate temporal/cohort structure, per-gene breakdowns, leave-one-gene-out, large-gene exclusion and predeclared batch-period sensitivity checks. Run these after the main pipeline is stable and keep them distinct from the primary comparison.

6. Gate A: report whether the primary comparison supports a temporal benefit; a null or negative result is acceptable. Gate B: aggregation correctness must already have passed. Gate C: complete the related-work checks before strong novelty claims.

7. Deliverables: per_origin_metrics.csv, paired_comparison.csv, ablation tables, calibration and drift plots, plus a narrative stating cohort, target, estimator, uncertainty limits and negative results. Exit gate: every report number can be regenerated from stored run IDs.

## 12. Phase 8 — outbox-driven MongoDB and Neo4j projections

1. Depends on: committed relational history; can begin once the vertical slice passes while later ML work continues. Implement a single polling worker with bounded batches, retries and per-consumer delivery state. The relational change and outbox row commit in the same transaction.

2. Use stable event IDs and deterministic document/edge keys. Retrying an event after a consumer write but before acknowledgement must not create duplicates. Maintain ordering/version checks per entity so an old retry cannot overwrite a newer projection.

3. MongoDB: scv_evidence for selected historical raw rows and available evidence, feature_vectors keyed by variant/origin/feature definition, prediction_explanations tied to the fitted run and ETL run summaries. Do not fill missing archived citations with current evidence and then use it as historical model input.

4. Neo4j: Submitter, Variant, Gene and Release nodes; historical ASSERTED episodes, IN_GENE and CHANGED edges. Preserve multiple observed intervals rather than replacing old assertion-edge properties with the newest version. Use the same half-open boundaries as PostgreSQL.

5. Implement the two planned graph use cases: submitter revisions preceding an aggregate change and gene-level counts of distinct drifted variants over a window. Do not label temporal precedence as causality.

6. Add a reconciliation command comparing expected relational episode/event identifiers with each projection and re-enqueueing missing items. Expose projection lag and last successfully processed event in the UI or health endpoint.

7. Failure tests: kill the worker after one consumer succeeds, replay the same batch, restart a consumer, send an older revision after a newer one and rebuild an empty projection entirely from the authoritative data. Exit gate: MongoDB and Neo4j are populated, queryable, duplicate-free under replay and independently reconstructible.

## 13. Phase 9 — API, evaluator interface and audit exports

1. Depends on: stable query services; use fixtures early, then real data. Build FastAPI endpoints around service functions rather than embedding SQL in Streamlit pages. Validate IDs, release visibility, horizon, limits and bounded result sizes.

2. Proposed endpoints: GET /releases; GET /variants/search; GET /variants/{id}/history?release=...; GET /variants/{id}/states; GET /changes?from=...&to=...; GET /audit-queue?run=...&origin=...&horizon=...; GET /models/{id}; GET /experiments/{id}/metrics; GET /health. Add evidence and graph-provenance endpoints only for implemented sources.

3. Streamlit screens: project/data coverage; variant time machine with a release selector and assertion provenance; drift explorer; audit queue with score/model/origin/horizon and matured outcome; benchmark comparison; import/projection health. Show the selected dataset revision and actual release coverage.

4. The history screen should distinguish assertion evaluation dates from observed visibility. The audit queue should distinguish pending outcomes from no-change outcomes and mark explanations as model attributions, not biological conclusions.

5. Provide CSV export for a selected queue and JSON export for the run manifest. Show an official-versus-calculated validation summary so the evaluator can inspect the aggregation gate, not only attractive charts.

6. Integration tests should cover one known fixture from source through history, state, event, prediction, outcome join and response; test invalid IDs and absent releases as well. Exit gate: the evaluator can follow one variant across three releases and trace one score to its source/run without manually editing the database.

## 14. Phase 10 — replay, performance, packaging and final demonstration

1. Depends on: an integrated application. Replay the frozen release sequence into a clean PostgreSQL database, rebuild the two projections and regenerate one baseline/model comparison. Save the commands and artifacts in a run manifest.

2. Benchmark time-travel and queue queries on the stated cohort, reporting warm/cold conditions, row counts, indexes and p50/p95 over repeated requests. Agree a local demo target after the slice measurements; do not claim subsecond performance merely because an index exists.

3. Compare incremental state/event maintenance with a full rebuild using exact canonical-row hashes plus wall-clock and peak memory. If a faster method disagrees, report the discrepancy and keep the correct method as the reference.

4. Run worker retry/reconciliation demonstrations, a database backup/restore test and a fresh-environment setup rehearsal. Keep a small deterministic offline demo bundle so a network failure does not prevent the evaluator from seeing the core workflow.

5. Final deliverables: source and locked dependencies; migrations and seed vocabularies; manifests and field mappings; tests and fixture data; import/validation logs; frozen dataset scope; model/run artifacts; metrics and plots; API/UI; projection-rebuild instructions; updated physical-schema notes; the accepted conceptual diagrams and evaluator script.

6. Demo sequence: load or select a recorded dataset revision → inspect a past release for one variant → show the later transition and provenance → show a genuinely as-of score and model cutoff → compare temporal/static/baseline metrics → show projection health and CSV export.

7. Keep source-reported pilot figures and toy checks separate from the current implementation measurements. Exit gate: a fresh machine/operator can reproduce the small demo and understand how to regenerate the full result set without relying on undocumented local state.

## 15. Test matrix and evidence to keep

1. Schema invariants: primary/foreign keys, composite event endpoints, no overlapping assertion episodes, prediction uniqueness, nonnegative counts and valid horizons. Evidence: migration/test output and failing-case fixtures.

2. Temporal invariants: unchanged content, changed content, disappearance/reappearance, open/closed ranges, adjacent-boundary containment, backdated evaluation, missing date and rejected out-of-order import. Evidence: fixed expected visible-SCV sets per origin.

3. ETL/recovery: duplicate input, modified artifact, partial source, concurrent import, crash before publication and exact rerun. Evidence: row-count/hash equality and import-state transitions; unchanged content does not inflate local revisions.

4. Aggregation: unanimous groups, selected-review disagreement, lower-review disagreement, unknown/somatic categories and duplicated submitters. Evidence: fixture results plus real official-match reports and a mismatch ledger.

5. Features/evaluation: future source reference rejection, label maturity, missing endpoints, horizon-three reversal, deterministic rank ties, no-positive origins and held-out tuning isolation. Evidence: fold manifests, row IDs and metric hand-checks.

6. Cross-store invariants: duplicate event delivery, consumer partial failure, stale event ordering and full projection rebuild. Evidence: counts/IDs and query outputs before and after replay.

7. End-to-end: a source fixture becomes an as-of response, a normalized event and a score/outcome response, then is exported. Evidence: one reproducible acceptance run and screenshots from the actual application.

8. Use unit tests for deterministic transformations and integration tests for database constraints and recovery. Run a small CI suite on every change; run the full historical benchmark only when code/contracts affecting it change. Avoid repeating expensive downloads for unrelated UI edits.

## 16. Work schedule and decision checkpoints

1. Week 1: contracts, field audit, environment, migrations, fixtures and the first three-release import. Target 20–35 hours. Checkpoint: source fields really support the planned identity/history and the temporal constraints work.

2. Week 2: state aggregation, mismatch investigation, history queries, event generation and validated vertical-slice demo. Target 25–40 hours. Checkpoint: no ML expansion until the aggregate target is defensible.

3. Week 3: full-window backfill, descriptive drift outputs, as-of features and outcome materialization. Target 25–40 hours. Checkpoint: enough mature examples and complete lineage; revise scope only through a recorded contract change.

4. Week 4: baselines, logistic regression, one boosted model, rolling-origin runs and first metrics. Target 25–40 hours. Checkpoint: no future leakage, no test-set tuning and no unsupported model-gain claim.

5. Week 5: document/graph projections, replay/reconciliation and API/UI integration. Target 25–45 hours. A second contributor can start projections after Week 2 while the primary model pipeline continues; the shared contracts remain sequential dependencies.

6. Week 6 and buffer: ablations, performance/rebuild comparison, recovery tests, reproducibility packaging and report/demo rehearsal. Target 20–40 hours. Source-format or aggregation problems can require extra weeks; revisit the estimate after the slice.

7. For a deadline-constrained submission, preserve the core: PostgreSQL history, validated states/events, baseline/static/temporal comparison, simple queue UI and working basic projections. Reduce optional sequence models, graph-following analysis and elaborate explanations first. This is a contingency ordering, not permission to label unfinished features complete.

8. Record completed acceptance gates, remaining work and observed time weekly. Treat negative model findings as results, while treating broken temporal reconstruction as an implementation defect that must be resolved.

## 17. First 48 hours: concrete tasks to start with

1. Task 1: create the implementation repository folders and a checklist from Phases 0–3. Keep the existing PDFs/draw.io as immutable design references. Add decisions.md describing the normalized core and the model-independent outcome refinement.

2. Task 2: choose the three-gene slice and three consecutive complete paired releases. Inspect both file headers, capture sample selected records and write a field-availability matrix. Verify germline channel, IDs and missing-value semantics before guessing column names.

3. Task 3: lock the environment and bring up PostgreSQL. Add the vocabularies, release manifest support, stable identities and assertion episode migration. Add the overlap/reappearance toy fixture and verify the as-of visible-version sets.

4. Task 4: write the streaming parser and deterministic filtered extract. Import the first accepted release, rerun it and compare canonical row hashes. Only then import the second and third releases.

5. Task 5: implement history(v, release), simple validated aggregation, state rows and normalized event joins. Compare a handful of real cases with the official same-release values and write down every mismatch.

6. First reviewable milestone: one command recreates the fixture database; one import command accepts the real slice; one history command shows old and new assertion episodes; a second identical import changes no logical facts. This is the foundation that everything else depends on.

## 18. Sources checked for this implementation plan

1. [S1] NCBI archived TSV directory: paired monthly filenames, release availability and listed compressed sizes. https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/

2. [S2] NCBI download guide and file primer: available formats, summary versus complete XML coverage and archive guidance. https://www.ncbi.nlm.nih.gov/clinvar/docs/downloads/ ; https://www.ncbi.nlm.nih.gov/clinvar/docs/ftp_primer/

3. [S3] PostgreSQL range documentation: GiST interval operations and exclusion constraints with btree_gist. https://www.postgresql.org/docs/18/rangetypes.html

4. [S4] scikit-learn TimeSeriesSplit reference: chronological indexed splits; this project adds grouped release origins and explicit label-maturity rules. https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html

5. [S5] scikit-learn average_precision_score reference: estimator definition, to distinguish average precision from trapezoidal PR area. https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html

6. Project-specific baseline: the reattached ClinVar Time Machine proposal, the latest accepted ER/mapping/DFD documents, the changes-only normalization PDF and the detailed defence guide. The effort estimates, phase boundaries, support-table choices and acceptance interfaces in this plan are implementation recommendations, not previously measured results.
