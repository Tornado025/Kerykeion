# Kerykeion evaluator walkthrough

For the current main prediction flow, open Predictions at November 2026. Choose a gene, current classification and 1-, 3- or 6-month probability window. Expand a forecast to see the monthly first-change distribution and the chance of no change within six months. The displayed waiting time is conditional on a change occurring within six months; it is not a promised date. Open Model checks to compare sooner-change ranking with timing error. The latter has barely improved over the baseline. The older fixed-window flow described below is retained under Earlier experiments.


Start Docker Desktop, then run `scripts/start_demo.sh` from the repository.
Open http://127.0.0.1:8001. PostgreSQL, MongoDB and Neo4j use persistent local
volumes; stopping the application does not remove the imported archives.

1. On Explore, choose February 2025. All imported month tabs stay visible.
   Open TP53 and search for Variation ID 188342.
2. On its variant page, switch between January and February. This example changed
   from the benign group to uncertain significance. The underlying variant keeps
   its identity; its recorded interpretation changed. Compare the expert-panel
   assertion episodes and evaluation date with their observed archive months.
3. Expand submitted evidence to read the historical MongoDB document. Inspect
   submission connections to see Neo4j organisation/assertion relationships.
   These connections represent provenance, not a three-dimensional molecule.
4. Open Predictions and choose a later starting month. Select 1 or 3 months ahead,
   then filter by gene and current classification. The top percentage is taken
   within that filtered group, not within the original all-gene shortlist.
5. Expand “Inputs used for this prediction”. These are the archived feature values
   used at scoring time; they are not causal explanations. Open the variant for
   the source submissions. Download the same filtered list as CSV.
6. For a historical origin with a known endpoint, enable “Show what happened later”.
   For the latest November 2026 origin, later outcomes are unknown and stay unknown.
   A low priority does not mean clinically benign, and a high priority does not
   mean pathogenic or an independently calibrated probability.
7. Open Prediction checks. Compare the fixed logistic and boosted methods using
   one snapshot versus earlier history. Each row identifies its starting month
   and horizon. Expand full-history results for the mean across evaluable months.
   Use `reports/RESULTS.md` for measured differences and uncertainty; do not infer
   an improvement from the existence of a temporal model.
8. On Releases, inspect source agreement and the three local service statuses.
   The reconstruction is explicitly validated against official archive groups;
   remaining discrepancies are listed in `reports/source_mismatches.csv`.

## Reproduce results

Use the README's finish_models, sensitivity, evaluate and verify_project commands.
`reports/run_manifest.json` identifies the source manifests, fitted run IDs,
software environment and statistical reporting protocol. All model training uses
past information and labels available by that model's origin. Parameters are fixed;
no final-outcome tuning is performed. The target compares endpoint groups, so an
intermediate change that reverses by the endpoint is not a positive outcome.

## Offline demo

The already imported data is fully usable without Internet access. For a fresh,
small offline rehearsal, create a separate PostgreSQL database, MongoDB database
and `KERYKEION_DATASET` namespace. Migrate it and run `backend.cli demo-fixture`,
then `backend.cli train`, `backend.cli project` and start the API with the same
environment variables. Fixtures are visibly labelled synthetic. Do not reuse the
real dataset's database or graph namespace.

## Back up and restore

A backup is a PostgreSQL custom-format dump; MongoDB and Neo4j can be rebuilt from
the authoritative relational outbox. Keep `.env`, selected source extracts and
`artifacts/models/` with the backup, outside Git.

```sh
docker compose exec -T postgres pg_dump -U kerykeion -Fc kerykeion > artifacts/kerykeion.dump
# Restore only into a NEW database you created for the rehearsal:
docker compose exec -T postgres createdb -U kerykeion kerykeion_restore_check
docker compose exec -T postgres pg_restore -U kerykeion -d kerykeion_restore_check < artifacts/kerykeion.dump
```

Use different MongoDB and graph dataset namespaces before replaying a restored
dataset alongside the original. `scripts.reconcile --consumer both` replays the
outbox and must run with the intended isolated environment.

## Scope

The delivered application uses BRCA1, BRCA2 and TP53 across 23 monthly archives.
The original longer research plan's approximately 70-gene expansion, sequence model
and optional biological structure viewer are extensions, not claimed here.
