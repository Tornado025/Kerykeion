"""Regenerate report tables and figures from saved, temporally valid runs."""
import csv,json,platform,sys,os
from collections import defaultdict
from pathlib import Path
import numpy as np
from backend.db import ROOT,connect
from backend.ml import metric_values
from backend.services import models,health

OUT=ROOT/'reports';OUT.mkdir(exist_ok=True)

def table(name,rows):
    if not rows:return
    with (OUT/name).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def block_interval(values,seed=42,block=3,repeats=2000):
    """Circular moving release-block bootstrap on paired origin differences."""
    a=np.asarray(values,dtype=float)
    if len(a)<3:return None
    rng=np.random.default_rng(seed);means=[]
    for _ in range(repeats):
        starts=rng.integers(0,len(a),size=int(np.ceil(len(a)/block)))
        sample=np.concatenate([a[(start+np.arange(block))%len(a)] for start in starts])[:len(a)]
        means.append(sample.mean())
    return [float(x) for x in np.quantile(means,[.025,.975])]


def main():
    runs=models();per_origin=[];paired=[];per_gene=[];calibration=[]
    lookup={(m['model_name'],m['feature_set'],m['origin_release_id'],m['horizon']):m for m in runs}
    with connect() as c:
        releases=c.execute('SELECT release_id,label,stats,manifest_sha256 FROM release ORDER BY release_id').fetchall()
        artifacts=c.execute('SELECT * FROM release_artifact ORDER BY release_id,kind').fetchall()
        mismatches=c.execute('SELECT v.variant_id,g.gene_symbol,r.label,x.official_class,x.calculated_class FROM validation_result x JOIN variant v USING(variant_id) JOIN gene g USING(gene_id) JOIN release r USING(release_id) WHERE NOT x.matches ORDER BY r.release_id,v.variant_id').fetchall()
        for m in runs:
            x=m['metrics'] or {};b=x.get('budget_5',{});population=x.get('scored',0)
            per_origin.append(dict(model_id=m['model_id'],method=m['model_name'],inputs=m['feature_set'],origin=m['origin_release_id'],starting_month=m['label'],horizon=m['horizon'],warmup_eligible=m['origin_release_id']>=6,scored=population,evaluable=x.get('evaluable',0),unknown=population-x.get('evaluable',0),changes=x.get('positives',0),average_precision=x.get('average_precision'),roc_auc=x.get('roc_auc'),brier=x.get('brier'),recall_1=x.get('budget_1',{}).get('recall'),recall_5=b.get('recall'),precision_5=b.get('precision'),lift_5=(b['precision']/(x['positives']/x['evaluable'])) if b.get('precision') is not None and x.get('positives') else None))
            if m['feature_set']=='temporal' and m['model_name'] in ('logistic','boosted'):
                other=lookup.get((m['model_name'],'static',m['origin_release_id'],m['horizon']))
                if other and x.get('average_precision') is not None and other['metrics'].get('average_precision') is not None:
                    paired.append(dict(method=m['model_name'],horizon=m['horizon'],origin=m['origin_release_id'],starting_month=m['label'],warmup_eligible=m['origin_release_id']>=6,static_run=other['model_id'],temporal_run=m['model_id'],ap_difference=x['average_precision']-other['metrics']['average_precision'],recall5_difference=x['budget_5']['recall']-other['metrics']['budget_5']['recall']))
            if m['model_name'] not in ('logistic','boosted') or m['origin_release_id']<6 or not x.get('evaluable'):continue
            rows=c.execute('''SELECT p.variant_id,p.score,p.realized_label,g.gene_symbol,a.matches AS origin_agrees,b.matches AS target_agrees FROM prediction_results p JOIN variant v USING(variant_id) JOIN gene g USING(gene_id)
              LEFT JOIN validation_result a ON a.variant_id=p.variant_id AND a.release_id=p.origin_release_id
              LEFT JOIN validation_result b ON b.variant_id=p.variant_id AND b.release_id=p.target_release_id WHERE p.model_id=%s''',(m['model_id'],)).fetchall()
            for gene in ('BRCA1','BRCA2','TP53','official_agreement_only'):
                selected=[r for r in rows if (r['origin_agrees'] and r['target_agrees'])] if gene=='official_agreement_only' else [r for r in rows if r['gene_symbol']==gene]
                ids=[r['variant_id'] for r in selected];labels={r['variant_id']:r['realized_label'] for r in selected if r['realized_label'] is not None}
                metrics=metric_values([r['score'] for r in selected],labels,ids)
                per_gene.append(dict(model_id=m['model_id'],method=m['model_name'],inputs=m['feature_set'],origin=m['origin_release_id'],horizon=m['horizon'],subset=gene,scored=len(ids),evaluable=metrics['evaluable'],changes=metrics['positives'],average_precision=metrics['average_precision'],recall5=metrics['budget_5']['recall']))
            bins=defaultdict(list)
            for r in rows:
                if r['realized_label'] is not None:bins[min(9,int(r['score']*10))].append(r)
            for bucket,rs in bins.items():calibration.append(dict(model_id=m['model_id'],method=m['model_name'],inputs=m['feature_set'],origin=m['origin_release_id'],horizon=m['horizon'],bin=bucket,n=len(rs),mean_score=sum(r['score'] for r in rs)/len(rs),observed_change_fraction=sum(r['realized_label'] for r in rs)/len(rs)))
    table('per_origin_metrics.csv',per_origin);table('paired_comparison.csv',paired);table('per_gene_metrics.csv',per_gene);table('calibration.csv',calibration);table('source_mismatches.csv',mismatches)
    intervals=[]
    for method in ('logistic','boosted'):
        for horizon in (1,3):
            group=sorted([r for r in paired if r['method']==method and r['horizon']==horizon and r['warmup_eligible']],key=lambda r:r['origin'])
            if group:
                values=[r['ap_difference'] for r in group];intervals.append(dict(method=method,horizon=horizon,origins=len(values),mean_ap_difference=float(np.mean(values)),release_block_95_interval=block_interval(values),block_length=3,seed=42,resamples=2000))
    manifest=dict(dataset=json.loads((ROOT/'config/project.json').read_text()),releases=releases,source_artifacts=artifacts,software=dict(python=sys.version,platform=platform.platform()),model_ids=[m['model_id'] for m in runs],warmup_releases=6,parameters='Fixed logistic regression and boosted-tree parameters. No future-outcome tuning or model selection.',uncertainty=intervals,services=health())
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2,default=str))
    (OUT/'summary.json').write_text(json.dumps(dict(runs=len(runs),paired_uncertainty=intervals,source_mismatches=len(mismatches)),indent=2))
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'artifacts/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for method in ('logistic','boosted'):
        rs=sorted([r for r in paired if r['method']==method and r['horizon']==1 and r['warmup_eligible']],key=lambda r:r['origin'])
        axes[0].plot([r['starting_month'] for r in rs],[r['ap_difference'] for r in rs],marker='o',label=method)
    axes[0].axhline(0,color='gray',linewidth=1);axes[0].set_title('Historical features minus snapshot: average precision');axes[0].tick_params(axis='x',rotation=75,labelsize=7);axes[0].legend()
    groups=defaultdict(list)
    for r in calibration:
        if r['horizon']==1:groups[(r['method'],r['inputs'],r['bin'])].append(r)
    for method in ('logistic','boosted'):
        rs=[]
        for b in range(10):
            group=groups.get((method,'temporal',b),[]);n=sum(x['n'] for x in group)
            if n:rs.append((sum(x['mean_score']*x['n'] for x in group)/n,sum(x['observed_change_fraction']*x['n'] for x in group)/n))
        if rs:axes[1].plot(*zip(*rs),marker='o',label=method)
    axes[1].plot([0,1],[0,1],color='gray',linestyle='--');axes[1].set(xlabel='Mean model score (uncalibrated)',ylabel='Observed change fraction',title='Reliability on evaluated months');axes[1].legend();fig.savefig(OUT/'model_results.png',dpi=180);plt.close(fig)
    lines=['# Kerykeion: measured results','',f"Dataset: {len(releases)} monthly releases, {releases[0]['label']} through {releases[-1]['label']}; BRCA1, BRCA2 and TP53.",'',f'Saved latest runs: {len(runs)}. The first six releases supply warm-up; paired reporting uses origins with available endpoint outcomes. Horizon 1 is primary and horizon 3 secondary.','', '## Temporal versus snapshot inputs','', '| Method | Horizon | Evaluated origins | Mean AP difference | 95% release-block interval |','|---|---:|---:|---:|---|']
    for r in intervals:lines.append(f"| {r['method']} | {r['horizon']} | {r['origins']} | {r['mean_ap_difference']:.5f} | {r['release_block_95_interval']} |")
    lines+=['','Intervals resample paired release blocks of length 3, 2,000 times with seed 42. They describe variability in this three-gene panel; they do not establish clinical validity or generalisation to other genes. Shared variants and few origins remain limitations.','',f"There are {len(mismatches)} variant-release reconstruction mismatches, listed in source_mismatches.csv. Primary labels concern the documented reconstruction. per_gene_metrics.csv includes a secondary analysis restricted to endpoints matching the official archive groups.",'','A no-change or negative model result is retained. Latest origins without future endpoints are predictions with unknown outcomes, not negative outcomes. Model scores are not calibrated probabilities.','', 'No hyperparameter search used future test outcomes. Static-versus-temporal is the primary feature-group ablation; additional sensitivity experiments are stored separately when run.','', '![Measured model comparisons](model_results.png)']
    (OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(reports=str(OUT),runs=len(runs),intervals=intervals),default=str))

if __name__=='__main__':main()
