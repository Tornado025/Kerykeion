# Historical expansion for next-change timing research

The final project target is 40 genes. The panel is deferred; the current historical expansion retains BRCA1, BRCA2 and TP53. More historical first-change events and longer follow-up are the immediate priority. No improvement in model performance is assumed from adding data.

## Source audit

The official 2023 and 2024 annual directories each list all 12 variant-summary and all 12 submission-summary archives. The committed inventory is `reports/research/historical-availability.json`. Sampled January headers from both years include VariationID, SCV, submitter, review status and ClinicalSignificance. The adapter already accepts that older classification field and the year-directory URL convention. Every complete downloaded month must still pass parsing, provenance and import checks; a header sample is not proof that all rows are compatible.

Sources: [2023 archive directory](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2023/), [2024 archive directory](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2024/), [NCBI release cycle](https://www.ncbi.nlm.nih.gov/clinvar/docs/release_cycle/).

## Isolated chronological import

The existing demo numbers releases chronologically starting at January 2025 and has saved predictions referencing those IDs. Earlier months cannot be appended to that catalogue. `scripts.expand_history` instead creates the PostgreSQL schema `research_history_2023_v1` and rebuilds January 2023–November 2026 in order, reusing the already downloaded 2025–2026 extracts. The default PostgreSQL schema, application release IDs, saved models and MongoDB/Neo4j projections are preserved.

The research corpus is a PostgreSQL-only analytical dataset. Its outbox is not consumed by the demo workers. It is not advertised as a published three-store application dataset. Model training and projection expansion are separate subsequent steps. Timing feature caches must also be namespaced before training on this history because its numeric release IDs differ from the demo.

Downloads use two range workers and imports run sequentially at lower scheduling priority. Complete-source hashes and selected extracts are retained by the existing adapter. Partial downloads resume from range checkpoints. A process lock prevents duplicate expansion workers; a chronological-prefix check prevents mixing histories.

Run from the repository:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 KERYKEION_DOWNLOAD_WORKERS=2 nice -n 10 .venv/bin/python -m scripts.expand_history
```

Progress: `artifacts/history-expansion/progress.json`; log: `artifacts/history-expansion.log`. Verified completion requires all 47 month labels in order, 94 source artifact records and final domain counts in `artifacts/history-expansion/verification.json`. A process launch is not completion.

## Research acceptance before modelling

Inspect monthly counts, selected-variant disappearance and reappearance, submission aliases, source field transitions and disagreement with the official classification group. Quantify distinct variants with first changes and class transitions; repeated landmark rows are not independent events. Earlier archives add training information, not a new untouched future test: May–October 2026 outcomes have already been inspected. Freeze an expanded-data protocol before comparing models, and label reused test periods as retrospective exploratory evidence. The eventual 40-gene panel must be chosen independently of favourable model performance.
