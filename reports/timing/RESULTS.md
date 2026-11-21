# Next-change timing results

Target: first future observed classification-group change. Reversals still count as an event. Missing observations and the archive endpoint censor follow-up; they are not future no-change labels.

Learned method selected on early development months: boosted_hazard. Selection used outcomes available by release 17 only. Later releases 17–22 are untouched evaluation origins; models refit only on information available by each origin.

| Method | Mean C-index | Event-only time MAE (months) |
|---|---:|---:|
| constant_hazard | 0.5000 | 1.600 |
| class_hazard | 0.7010 | 1.596 |
| boosted_hazard | 0.8555 | 1.588 |

C-index measures which variants change sooner, not accuracy of a calendar date. Tied monthly event times are omitted. Event-only MAE excludes censored records and must not be interpreted as overall timing accuracy.

Cumulative event probabilities are evaluated with IPCW Brier scores at observable horizons. Censor survival is estimated from each held-out landmark for evaluation only, with the discrete convention that a censor at month k has known status through k. Horizon-specific coverage and all counts are in results.json. Late origins have less than six months of follow-up; do not compare their integrated scores as identical-horizon tests.

Calibration uses only later past months available by the prediction origin. Negative exposure sampling retains all events and uses inverse sampling weights, preserving the rare event rate. No balanced class weights or artificial event prevalence are presented as calibrated probabilities.

If cumulative change probability never reaches 50% within six months, there is no supported median change month. The UI says this explicitly rather than inventing a date. A conditional timing estimate assumes a change occurs within the six-month window; it does not assert that one will occur.

These results are limited to three genes and monthly reconstructed interpretation groups. The earlier endpoint-change reports remain separate; their precision/recall values do not measure next-change timing.
