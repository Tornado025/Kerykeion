# Predicting when the next change occurs

## Question and event

For a variant observed in a starting archive, estimate the monthly distribution of its **first subsequent classification-group change**. We do not predict the destination class. A change followed by a reversal still counts at the first change. This differs from comparing only the starting and ending classes, which can miss reversals.

The observation unit is a variant at a historical monthly starting point. Monthly archives establish when a change was first observed, not its exact clinical decision date. The current scope is BRCA1, BRCA2 and TP53, January 2025–November 2026.

## Follow-up and censoring

Follow-up stops at the first change, the first missing variant observation, the available archive endpoint, or six months. A missing future observation is censored; it is not a negative example. Observations after a gap are not used to silently bridge that gap.

## Model and training

Each observed month before an event contributes a person-period row. The model estimates the chance of first change in that month given survival without change to that month. Monthly event masses are combined into cumulative 1-, 3- and 6-month probabilities. Historical inputs include current interpretation and review information, submission disagreement, prior changes and time since those observations. No future archive features are used.

Candidates are a constant historical hazard, a class-specific historical hazard, weighted logistic regression and histogram gradient boosting. Training keeps all event exposures and samples 2.5% of negative exposures with inverse sampling weights. This preserves event prevalence rather than treating balanced training frequencies as probabilities. Boosting uses 100 iterations, seven leaves, minimum leaf size 150 and L2 regularisation 30. CPU training runs sequentially with one numerical-library thread.

Learned fits reserve the latest three available past months for weighted sigmoid calibration. Base-fit labels stop before that calibration period; calibration outcomes stop at the prediction origin. Model artifacts record source, fit and calibration cutoffs and a SHA-256 digest.

## Evaluation and selection

Development origins are August, October and November 2025. Selection uses only outcomes available by May 2026. Among the learned candidates, boosting had the lower development three-month IPCW Brier score. It did **not** beat the simple baselines on that development score. The later test results must not be used to retune and then described as untouched tests.

Test origins are May–October 2026, each fitted using only information available by its origin. Available follow-up is respectively six, five, four, three, two and one months. Consequently only one origin supports a complete six-month evaluation.

C-index measures whether comparable pairs are ordered by earlier change. Tied monthly event times are omitted. It is not calendar-month accuracy. IPCW Brier scores evaluate cumulative probabilities at observable horizons; the censor distribution is estimated within each test fold for evaluation only. Event-only timing MAE compares observed event times with the expected month conditional on an event within six months. It excludes censored records, and short follow-up selects earlier observed events; it cannot establish overall timing accuracy.

| Method | Mean C-index | Event-only timing MAE, months |
|---|---:|---:|
| Constant historical hazard | 0.5000 | 1.600 |
| Current-class historical hazard | 0.7010 | 1.596 |
| Boosted monthly hazard | 0.8555 | 1.588 |

The strong result is ordering sooner changes. Point timing improves by only 0.008 months against the class baseline, which is practically negligible. Precise timing remains weak. Probability evaluation improves on these held-out origins, but rare events, three selected genes and limited follow-up constrain the claim.

## What the interface means

“Chance within three months” includes all first events in months one through three. “Expected wait if a change occurs within six months” assumes that event; it does not say the variant will change. The six monthly event probabilities plus the probability of no event through six months sum to one. If the cumulative probability never reaches 50%, there is no supported median change month. The interface says this rather than inventing a date.

The two timing tables store a run and its per-variant probability curves. The earlier endpoint model tables remain historical experiments. Timing forecasts are currently saved for May–November 2026; older archive tabs remain visible and explain when no timing run exists.

## Reproduce and improve

Run migrations, then `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 .venv/bin/python -m scripts.train_timing`. Reports are in `reports/timing/`; artifacts and progress are in `artifacts/timing/` and `artifacts/timing-progress.json`.

Further research should compare the complete waiting-time distribution against stronger survival baselines, inspect calibration by gene and starting class, and report uncertainty across time origins. More historical first-change events and longer follow-up are needed to judge month estimates. Reserve a new future archive for prospective evaluation before tuning against the current test outcomes. Additional model complexity is an experiment, not a guaranteed improvement.

Method references: [survival evaluation](https://scikit-survival.readthedocs.io/en/stable/user_guide/evaluating-survival-models.html), [survival and censoring](https://scikit-survival.readthedocs.io/en/stable/user_guide/00-introduction.html), [probability calibration](https://scikit-learn.org/stable/modules/calibration.html). The implementation uses scikit-learn with explicit discrete-time calculations, not scikit-survival estimators.
