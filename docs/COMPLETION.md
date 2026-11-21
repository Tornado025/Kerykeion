## Next-change timing update

The main interface now uses the separate first-change timing model. Its implementation passed 17 backend tests; the frontend passed 13 tests and a production build. See [TIMING_MODEL.md](TIMING_MODEL.md). The historical acceptance figures below describe the earlier endpoint demo and its 20-table backup, before the two timing tables were added. They do not establish exact-month predictive accuracy.

# Earlier endpoint-demo acceptance evidence

The agreed BRCA1 / BRCA2 / TP53 local demo is implemented and verified. These acceptance figures cover the three-gene demo. The final research scope is now 40 genes, with the panel deferred; historical expansion is documented in HISTORICAL_EXPANSION.md.

- Archives: 23 months; 46 full-source provenance records.
- States: 896,935; assertion episodes: 173,721; recorded changes: 2,412.
- Saved prediction rows: 13,913,084; immutable input vectors: 1,793,870.
- Both one- and three-release prediction horizons are trained and evaluated chronologically.
- PostgreSQL, MongoDB and Neo4j passed reconciliation counts; both delivery backlogs are zero.
- Backend: 14 non-projection tests passed, plus the cross-store projection test passed (15 total). Frontend: 12 tests passed and the production build passed.
- Full backup/restore rehearsal passed: 20 table counts matched, with additional domain-row fingerprints. Backup size: 237,090,055 bytes.
- Docker container limits total 2.5 GiB, with reduced CPU allowances. Run heavy maintenance jobs sequentially.

## Measured API latency

Local warmed requests, 10 repetitions after the first request. These are measurements for this laptop and cohort, not a public-service latency guarantee.

| Endpoint | First request ms | Warm p50 ms | Warm p95 ms |
|---|---:|---:|---:|
| `/api/releases` | 32.5 | 9.7 | 13.0 |
| `/api/genes?release=23` | 32.8 | 22.1 | 24.1 |
| `/api/variants/188342?release=2` | 138.8 | 16.4 | 25.4 |
| `/api/audit-queue?budget=1&classification=B&gene=BRCA1` | 89.1 | 66.5 | 109.6 |
| `/api/experiments/summary` | 12.0 | 11.8 | 16.1 |

## Interpretation

The experiment does not establish a consistent temporal-feature advantage: the one-month boosted difference is positive on average but its release-block interval includes zero; logistic and three-month differences are negative on average. Retain the measured results rather than claim a model win. The fixed production default is a demonstrator, not a method chosen using future test labels.

The source mismatch ledger contains 547 variant-release differences out of 896,935 states. Primary outcomes refer to the documented reconstructed groups; agreement-only and per-gene results are exported separately. Scores are uncalibrated priorities. Prose-only evidence revisions and external clinical validation remain limitations.

See `../reports/RESULTS.md`, `DEMO_GUIDE.md`, `PHYSICAL_SCHEMA.md` and the repository README for reproduction and evaluator instructions.
