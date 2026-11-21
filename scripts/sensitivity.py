"""Predeclared fixed-setting sensitivities at the latest fully observed h1 origin.

These checks never select a production model. Results are exported separately.
"""
import json
from collections import defaultdict
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from backend.db import ROOT,connect
from backend.ml import STATIC,TEMPORAL,metric_values


def main():
    with connect() as c:
        origin=c.execute('SELECT max(origin_release_id) n FROM prediction_outcome WHERE horizon=1').fetchone()['n']
        test_rows=c.execute("SELECT f.variant_id,f.features,g.gene_symbol FROM feature_materialization f JOIN variant v USING(variant_id) JOIN gene g USING(gene_id) WHERE f.origin_release_id=%s AND f.feature_set='temporal' ORDER BY variant_id",(origin,)).fetchall()
        labels={r['variant_id']:r['realized_label'] for r in c.execute('SELECT variant_id,realized_label FROM prediction_outcome WHERE origin_release_id=%s AND horizon=1',(origin,))}
        count=c.execute("SELECT count(*) n FROM feature_materialization f JOIN prediction_outcome o USING(variant_id,origin_release_id) WHERE f.feature_set='temporal' AND o.horizon=1 AND o.target_release_id<=%s",(origin,)).fetchone()['n']
        if not test_rows or not count:raise ValueError('Finish feature materialization before sensitivity checks')
        keys=STATIC+TEMPORAL
        x=np.empty((count,len(keys)));y=np.empty(count,dtype=np.uint8)
        with c.cursor(name='sensitivity_features') as cur:
            cur.execute("SELECT f.features,o.realized_label FROM feature_materialization f JOIN prediction_outcome o USING(variant_id,origin_release_id) WHERE f.feature_set='temporal' AND o.horizon=1 AND o.target_release_id<=%s ORDER BY origin_release_id,variant_id",(origin,))
            for i,row in enumerate(cur):x[i]=[row['features'][k] for k in keys];y[i]=row['realized_label']
    test=np.array([[r['features'][k] for k in keys] for r in test_rows]);ids=[r['variant_id'] for r in test_rows]
    groups={'activity':['releases_since_submission','arrivals_1','arrivals_3','arrivals_6','new_submitters_3','recent_revision_share'],'past_changes':['past_changes','releases_since_change'],'deltas':['assertion_delta','submitter_delta','p_delta','v_delta','b_delta'],'evaluation_age':['newest_evaluation_age','oldest_evaluation_age','evaluation_missing_fraction']}
    jobs=[('all_features',keys),('snapshot_only',STATIC)]+[(f'without_{name}',[k for k in keys if k not in columns]) for name,columns in groups.items()]
    results=[]
    for name,columns in jobs:
        indices=[keys.index(k) for k in columns];model=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,random_state=42)
        model.fit(x[:,indices],y);scores=model.predict_proba(test[:,indices])[:,1]
        results.append(dict(check=name,origin=origin,train_rows=len(y),features=columns,metrics=metric_values(scores,labels,ids)))
        print(name,flush=True)
        if name=='all_features':
            # Shuffle temporal feature blocks together within each gene at the test origin.
            # Keeps class/gene composition and temporal marginals, breaks linkage to variant.
            shuffled=test.copy();rng=np.random.default_rng(42);cols=np.arange(len(STATIC),len(keys))
            for gene in ('BRCA1','BRCA2','TP53'):
                rows=np.array([i for i,r in enumerate(test_rows) if r['gene_symbol']==gene])
                shuffled[np.ix_(rows,cols)]=test[np.ix_(rng.permutation(rows),cols)]
            shuffled_scores=model.predict_proba(shuffled)[:,1]
            results.append(dict(check='history_shuffle_within_gene',origin=origin,train_rows=len(y),metrics=metric_values(shuffled_scores,labels,ids)))
    # Gene indicators occupy the final three static positions. Held-out gene never trains.
    for gene in ('BRCA1','BRCA2','TP53'):
        index=keys.index('gene_'+gene);train_mask=x[:,index]==0;test_mask=test[:,index]==1
        model=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,random_state=42)
        model.fit(x[train_mask],y[train_mask]);scores=model.predict_proba(test[test_mask])[:,1]
        gene_ids=[ids[i] for i in np.flatnonzero(test_mask)]
        results.append(dict(check='leave_out_'+gene,origin=origin,train_rows=int(train_mask.sum()),metrics=metric_values(scores,labels,gene_ids)))
        print('leave_out_'+gene,flush=True)
    out=ROOT/'reports/sensitivity.json';out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dict(seed=42,horizon=1,origin=origin,method='boosted',selection='Predeclared checks; no production model selection',results=results),indent=2))
    print(out)

if __name__=='__main__':main()
