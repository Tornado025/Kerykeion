"""Develop on early origins, freeze choice, then test later timing predictions."""
import json,time
import numpy as np
from backend.db import ROOT,migrate
from backend.timing import Dataset,HazardModel,curve,timing_metrics,save_forecast

OUT=ROOT/'reports/timing';OUT.mkdir(parents=True,exist_ok=True)
NAMES=['constant_hazard','class_hazard','logistic_hazard','boosted_hazard']
DEVELOPMENT=[8,10,11]
HOLDOUT=[17,18,19,20,21,22]


def progress(**state):
    state['updated_at']=time.time();(ROOT/'artifacts/timing-progress.json').write_text(json.dumps(state));print(json.dumps(state),flush=True)


def evaluate(data,model,origin):
    ids,x=data.inputs(origin);_,cumulative=curve(model.predict(x));duration,event=data.truth(origin,data.last,ids)
    return timing_metrics(duration,event,cumulative)


def main():
    migrate();data=Dataset();assert data.last>=23
    development=[]
    for origin in DEVELOPMENT:
        for name in NAMES:
            progress(stage='development',origin=origin,method=name)
            model=HazardModel(name).fit(data,origin)
            metrics=evaluate(data,model,origin)
            development.append(dict(origin=origin,method=name,metrics=metrics))
    # Outcomes for development origin 11 over six months mature at origin 17.
    # Choice is frozen before any later-origin holdout outcomes are examined.
    scores={}
    for name in NAMES:
        rows=[r for r in development if r['method']==name]
        brier=np.mean([next(h['ipcw_brier'] for h in r['metrics']['horizons'] if h['months']==3) for r in rows])
        scores[name]=float(brier)
    # Select a learned candidate using development Brier only; compare it with
    # both stronger baselines on untouched later origins. No forced model win.
    selected=min(['logistic_hazard','boosted_hazard'],key=lambda name:scores[name])
    selection=dict(development_origins=DEVELOPMENT,selection_outcome_cutoff=17,holdout_origins=HOLDOUT,rule='lowest development three-month IPCW Brier among learned candidates',development_scores=scores,selected=selected)
    (OUT/'selection.json').write_text(json.dumps(selection,indent=2))
    holdout=[]
    for origin in HOLDOUT:
        for name in ['constant_hazard','class_hazard',selected]:
            progress(stage='holdout',origin=origin,method=name)
            model=HazardModel(name).fit(data,origin);metrics=evaluate(data,model,origin)
            run_id=save_forecast(data,origin,model,metrics,selection) if name==selected else None
            holdout.append(dict(origin=origin,method=name,run_id=run_id,metrics=metrics))
    progress(stage='latest_forecast',origin=data.last,method=selected)
    model=HazardModel(selected).fit(data,data.last)
    rid=save_forecast(data,data.last,model,{},selection)
    result=dict(target='time until next observed classification-group change',resolution='monthly archives, not exact dates',months=6,development=development,selection=selection,holdout=holdout,latest_run=rid)
    (OUT/'results.json').write_text(json.dumps(result,indent=2))
    lines=['# Next-change timing results','', 'Target: first future observed classification-group change. Reversals still count as an event. Missing observations and the archive endpoint censor follow-up; they are not future no-change labels.','',f'Learned method selected on early development months: {selected}. Selection used outcomes available by release 17 only. Later releases 17–22 are untouched evaluation origins; models refit only on information available by each origin.','', '| Method | Mean C-index | Event-only time MAE (months) |','|---|---:|---:|']
    for name in ['constant_hazard','class_hazard',selected]:
        rows=[r['metrics'] for r in holdout if r['method']==name]
        ci=[r['concordance'] for r in rows if r['concordance'] is not None];mae=[r['event_only_timing_mae_months'] for r in rows if r['event_only_timing_mae_months'] is not None]
        lines.append(f"| {name} | {np.mean(ci):.4f} | {np.mean(mae):.3f} |")
    lines+=['','C-index measures which variants change sooner, not accuracy of a calendar date. Tied monthly event times are omitted. Event-only MAE excludes censored records and must not be interpreted as overall timing accuracy.','', 'Cumulative event probabilities are evaluated with IPCW Brier scores at observable horizons. Censor survival is estimated from each held-out landmark for evaluation only, with the discrete convention that a censor at month k has known status through k. Horizon-specific coverage and all counts are in results.json. Late origins have less than six months of follow-up; do not compare their integrated scores as identical-horizon tests.','', 'Calibration uses only later past months available by the prediction origin. Negative exposure sampling retains all events and uses inverse sampling weights, preserving the rare event rate. No balanced class weights or artificial event prevalence are presented as calibrated probabilities.','', 'If cumulative change probability never reaches 50% within six months, there is no supported median change month. The UI says this explicitly rather than inventing a date. A conditional timing estimate assumes a change occurs within the six-month window; it does not assert that one will occur.','', 'These results are limited to three genes and monthly reconstructed interpretation groups. The earlier endpoint-change reports remain separate; their precision/recall values do not measure next-change timing.']
    (OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    progress(stage='complete',latest_run=rid)

if __name__=='__main__':main()
