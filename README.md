# Kerykeion

A release-aware ClinVar research application: historical assertion versions, reconstructed variant states, change auditing and time-ordered review queues. The React interface follows the caduceus design reference: Helvetica Neue, a flat white canvas, thin list dividers and restrained red/blue accents.

## Research expansion

The planned final scope is **40 genes**; the panel is deferred. Historical expansion currently retains BRCA1, BRCA2 and TP53 and targets January 2023–November 2026 in an isolated research schema. See [historical expansion](docs/HISTORICAL_EXPANSION.md) for the source audit, progress files and verification requirements. This is ongoing data preparation, not a new performance result.

## Predicting the next change

The primary prediction target is **when the next observed classification-group change occurs**, at monthly resolution. Predictions use a six-month discrete survival model with historical features and past-only calibration. The main Predictions and Model checks pages now show this target. Earlier fixed-window endpoint experiments remain available separately. See [timing model](docs/TIMING_MODEL.md) and [measured results](reports/timing/RESULTS.md). Ranking sooner changes improved; reliable exact-month prediction has not been established.

## Stack

- React + TypeScript + Vite frontend, production-served by FastAPI
- PostgreSQL 16: normalized history, states, events, runs and outcomes
- MongoDB 7: historical submitted evidence, immutable feature vectors and per-run feature-context documents
- Neo4j 5: assertion episodes, submitter/variant/gene connections and release changes
- scikit-learn: logistic regression and boosted trees, alongside transparent heuristics

## Local setup

Use Python 3.12 and Node 24 (or a Vite-supported Node version). Docker Desktop must be running.

```bash
cp .env.example .env
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock
docker compose up -d
.venv/bin/python -m backend.cli migrate
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

Open http://127.0.0.1:8001. Keep the server bound to loopback: the provided database passwords are local demo defaults, not a public deployment configuration. For frontend development run `npm --prefix frontend run dev`; Vite proxies `/api` to port 8001.

## Import the initial real-data slice

```bash
.venv/bin/python -m etl.fetch 2025-01 2025-02 2025-03
.venv/bin/python -m scripts.build_demo 2025-01 2025-02 2025-03
```

The adapter selects unambiguous GRCh38 records for BRCA1 (672), BRCA2 (675) and TP53 (7157). It reads the historical germline classification column; somatic-specific columns are not used as classification labels. The source has no submitter identifier in the selected TSV format, so names receive stable hashed local identifiers. Unambiguous name changes supported by unchanged SCV and variant ownership are recorded as aliases; conflicting ownership remains an import error.

The first fetch transfers full public compressed source files, using six verified range workers and checkpoint files. Filtering reduces retained data, not network transfer. After a complete selected extract is atomically saved, raw compressed downloads are removed. Selected extracts are cached in ignored `data/extracts/`, with complete-source SHA-256s, URLs, byte counts and header mappings. No source files or data dumps are committed.

Submission archives have explanatory text before their actual tabular header. The adapter searches for the `VariationID` header rather than treating the first line as a column name. Archives from 2025 onward are supported in the top-level monthly directory; earlier years use year subdirectories. A changed archive format must be inspected rather than guessed.

For an unattended import alongside a still-running fetch, use `scripts.build_demo --wait ...`. Its durable status is `artifacts/demo-progress.json`; logs can be redirected to `artifacts/build-demo.log`. The script publishes each complete release, scores runs and replays projections. The first release supplies history but cannot train a future-change model by itself.

## Add a later archive during the demo

```bash
.venv/bin/python -m etl.fetch 2025-04
# Generate and save origin-3 scores before importing the new endpoint:
.venv/bin/python -m backend.cli train --origin 3 --horizon 1
# Publish April, refresh outcomes/metrics, and replay projections:
.venv/bin/python -m scripts.build_demo 2025-04
.venv/bin/python -m scripts.report
```

No schema change is needed to add a later month. The React release catalogue polls for accepted imports. An explicitly selected old release remains pinned. If the exact selected extract is imported again, the importer returns `unchanged`; a different manifest for an already published month is rejected. Never mix synthetic fixtures and real archives in the same dataset.

## What works and what it means

- Gene/variant searches, class filters, pagination and release selection
- Historical assertions selected by `[first_release, last_release)` visibility; old views exclude later states, events and realized outcomes
- A normalized event view reconstructs source/destination classes from endpoint states
- Official-versus-reconstructed group comparisons for each variant/release, including explicit mismatches
- Outbox delivery with independent MongoDB and Neo4j acknowledgements; retries do not duplicate documents or assertion edges
- Variant evidence fetched from MongoDB and an SVG connection view backed by Neo4j records; this is **not** a 3D molecular structure viewer
- Immutable as-of feature vectors, rolling-origin runs and deterministic review ranking
- Average precision, ROC-AUC, Brier score and review-budget precision/recall; undefined/pending values remain distinct from zero
- CSV queue export, API docs at `/docs` and service/backlog status on Releases

The primary target implemented here is reconstructed **endpoint group change**, not clinical truth or disease risk. Groups are P/V/B/C/O. A horizon-three change and reversal is negative when the endpoint groups match. Review-only events are separate. Outcomes are stored once per variant/origin/horizon and joined to model scores. The imported window is January 2025–November 2026. Rolling-origin runs and measured comparisons are generated by the commands below; a model benefit is reported only if supported by those results.

The aggregation policy selects the highest reviewed known classification group; disagreement there gives C. Counts describe all visible selected assertions. The policy is a transparent reconstruction, not a universal reimplementation of every ClinVar rule. Inspect agreement on Releases before interpreting results. Source modification dates are retained as archive dates and checked against the month; local import timestamps are separate.

The current temporal feature subset includes state changes/recency, assertion and submitter deltas, visible assertion arrival windows, evaluation-date ages/missingness and recent tracked revisions. `history_length` explicitly records partial early history. Larger-cohort research extensions include complete submitter-rate features, stronger warm-up protocols, paired uncertainty intervals, ablations and held-out final-origin tuning. The simple small-window benchmark should not be reported as those completed experiments.

Model artifacts live under ignored `artifacts/models/`. An existing run is keyed by its source cutoff, model configuration, feature definition and implementation hash. Labels mature only after an endpoint arrives; training outcomes must be observed by the test origin. Local feature-context explanations expose the inputs; they are not fabricated SHAP values or causal explanations.

## Projections and health

```bash
.venv/bin/python -m backend.cli project
.venv/bin/python -m backend.cli health
.venv/bin/python -m scripts.report
```

Projection delivery is eventual, not one transaction across all three stores. Pending counts are visible on Releases. Historical SCV episode keys prevent duplicate graph edges. Replaying an older event reads the current authoritative intervals, so it cannot reopen a newer closed episode.

The API is read-only by default. The optional projection-replay endpoint requires an explicit `WRITE_TOKEN` header configured through `.env`. Archive imports remain deliberate local CLI operations.

## Tests

```bash
RUN_DB_TESTS=1 .venv/bin/python -m pytest -q
# Include both other stores, with disposable test namespaces:
RUN_DB_TESTS=1 RUN_PROJECTION_TESTS=1 .venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Database tests create disposable schemas and clean only those schemas. Projection tests use UUID-prefixed test namespaces/databases and remove only their own fixtures. Synthetic fixture records are clearly tagged and are never presented as archive observations. CI runs PostgreSQL integration tests and React build/tests; the cross-store replay test is opt-in locally.

## Reproducibility and scope

`config/project.json` names the dataset contract; migrations document physical facts and support tables. Use a separate database/schema and projection namespace for a changed cohort, parser or aggregation contract. Do not rewrite sealed history behind existing predictions. The sample DDL plus operational metadata is intentionally more detailed than the conceptual ER.

`artifacts/verification-report.json` is generated from actual current rows and service queries. `docs/decisions.md` explains temporal and normalization choices. The project imports public ClinVar archives; no patient-level input is requested.

### Archive-only backfill

To fetch, import and project a chronological list without training models:

```sh
.venv/bin/python -m scripts.backfill 2025-03 2025-04
```

Each complete extract is cached; repeated identical imports are idempotent. The
runner stops on errors instead of skipping a month. Inspect
`artifacts/backfill-progress.json` and the redirected log for progress. Stop the
runner to pause; run the same month list again to resume. Only BRCA1, BRCA2 and
TP53 are selected from the full archives. Check NCBI's paired monthly archive
listing before requesting a month; November 2026 was not published when checked
on 2 November 2026 (paired files were available through October 2026).


## Complete the prediction experiments and reports

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venv/bin/python -m scripts.finish_models
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venv/bin/python -m scripts.sensitivity
.venv/bin/python -m scripts.evaluate
.venv/bin/python -m scripts.report
.venv/bin/python -m scripts.verify_project
```

The model job saves each completed run before advancing and can be rerun safely.
It fits both one- and three-release horizons with fixed parameters and training
labels matured by each starting month. Existing matching runs are reused and their
outcomes re-evaluated. Progress is in `artifacts/model-progress.json`. Reports use
six releases of history before primary comparisons; early cold-start runs remain
available for transparency. Scores are uncalibrated review priorities.

`reports/RESULTS.md`, CSV tables, `model_results.png` and `run_manifest.json` are
regenerated from saved database run IDs. Sensitivities include historical feature
group removals, shuffled historical inputs within gene, and leave-one-gene-out.
These are diagnostic experiments at the last fully observed one-month origin;
they do not select the production method or justify generalisation to other genes.

Start the application with `scripts/start_demo.sh`. See `docs/DEMO_GUIDE.md` for
the evaluator walkthrough and backup/restore commands. An isolated offline demo
uses the deterministic synthetic fixtures; never import them into the real data
schema. Override `KERYKEION_DATASET` along with the database and MongoDB namespace
when using a separate demo dataset, so Neo4j identities remain isolated too.

The three-gene cohort remains the agreed scope. Broader gene coverage and optional
sequence/3D structure models are outside this delivered demo. Existing accepted
ER, mapping, DFD and normalisation PDFs remain in `docs/deliverables/`.


### Laptop resource limits

Compose limits PostgreSQL to 768 MiB / 1 CPU, MongoDB to 768 MiB / 0.75 CPU
(with a 256 MiB WiredTiger cache), and Neo4j to 1 GiB / 0.5 CPU. Docker Desktop
itself adds VM overhead. Run training, report generation, projection replay and
backup rehearsals sequentially on a laptop. Model context documents reference
immutable feature vectors per run rather than duplicating inputs for every score.
`python -m scripts.project_models` drains pending delivery without retraining.

## Email and password accounts

The app now requires an email/password session. Password reset uses a six-digit email OTP delivered by SendGrid. Configure `SENDGRID_API_KEY` and `SENDGRID_FROM_EMAIL` in the ignored local `.env`, apply migrations, rebuild the frontend, and restart the API. See [authentication setup](docs/AUTHENTICATION.md) for configuration and verification.
