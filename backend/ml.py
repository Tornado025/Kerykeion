"""Release-grouped rolling-origin evaluation. Future outcomes never enter features."""
import hashlib,json,math
from collections import defaultdict
from datetime import date
import numpy as np
from psycopg.types.json import Jsonb
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score,roc_auc_score,brier_score_loss
from backend.db import connect
from etl.importer import digest,enqueue

STATIC=['class_P','class_V','class_B','class_C','class_O','stars','submitters','assertions','n_p','n_vus','n_b','gene_BRCA1','gene_BRCA2','gene_TP53']
TEMPORAL=['history_length','releases_since_submission','past_changes','releases_since_change','assertion_delta','submitter_delta','p_delta','v_delta','b_delta','arrivals_1','arrivals_3','arrivals_6','new_submitters_3','newest_evaluation_age','oldest_evaluation_age','evaluation_missing_fraction','recent_revision_share']

def features(conn,origin,feature_set):
    rows=conn.execute('SELECT s.*,v.gene_id FROM variant_state s JOIN variant v USING(variant_id) WHERE release_id<=%s ORDER BY variant_id,release_id',(origin,)).fetchall()
    histories=defaultdict(list)
    for r in rows:histories[r['variant_id']].append(r)
    observations=conn.execute('''SELECT a.variant_id,a.submitter_id,a.first_release_id AS arrived,v.version_no,v.first_release_id,v.class_code,v.date_evaluated FROM clinical_assertion a JOIN assertion_version v USING(scv_accession)
      WHERE int4range(v.first_release_id,v.last_release_id,'[)') @> %s::integer''',(origin,)).fetchall()
    obs=defaultdict(list)
    for r in observations:obs[r['variant_id']].append(r)
    origin_date=conn.execute('SELECT release_date FROM release WHERE release_id=%s',(origin,)).fetchone()['release_date']
    result={}
    for vid,h in histories.items():
        s=h[-1]
        if s['release_id']!=origin:continue
        f={f'class_{k}':int(s['aggregate_class']==k) for k in 'PVBCO'}
        f.update(stars=s['review_stars'],submitters=s['submitter_count'],assertions=s['assertion_count'],n_p=s['n_p'],n_vus=s['n_vus'],n_b=s['n_b'])
        f.update({f'gene_{name}':int(s['gene_id']==gid) for name,gid in [('BRCA1',672),('BRCA2',675),('TP53',7157)]})
        if feature_set=='temporal':
            changes=[b['release_id'] for a,b in zip(h,h[1:]) if a['aggregate_class']!=b['aggregate_class'] and b['release_id']==a['release_id']+1]
            prev=h[-2] if len(h)>1 else s
            observations=obs[vid];arrived={r['arrived'] for r in observations}
            ages=[max(0,(origin_date-r['date_evaluated']).days) for r in observations if r['date_evaluated']]
            f.update(history_length=len(h),releases_since_submission=origin-max((r['first_release_id'] for r in observations),default=origin),past_changes=len(changes),releases_since_change=origin-(changes[-1] if changes else h[0]['release_id']),assertion_delta=s['assertion_count']-prev['assertion_count'],submitter_delta=s['submitter_count']-prev['submitter_count'],p_delta=s['n_p']-prev['n_p'],v_delta=s['n_vus']-prev['n_vus'],b_delta=s['n_b']-prev['n_b'])
            for w in (1,3,6):f[f'arrivals_{w}']=sum(r['arrived']>origin-w for r in observations)
            f['new_submitters_3']=len({r['submitter_id'] for r in observations if r['arrived']>origin-3})
            f.update(newest_evaluation_age=min(ages) if ages else -1,oldest_evaluation_age=max(ages) if ages else -1,evaluation_missing_fraction=1-len(ages)/max(1,len(observations)),recent_revision_share=sum(r['version_no']>1 and r['first_release_id']>origin-3 for r in observations)/max(1,len(observations)))
        fh=digest(f)
        existing=conn.execute('SELECT feature_hash FROM feature_materialization WHERE variant_id=%s AND origin_release_id=%s AND feature_set=%s',(vid,origin,feature_set)).fetchone()
        if existing and existing['feature_hash']!=fh:raise ValueError('Frozen as-of feature changed: new dataset/feature version required')
        conn.execute('INSERT INTO feature_materialization VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(vid,origin,feature_set,Jsonb(f),origin,fh))
        result[vid]=f
    return result

def metric_values(scores,labels,variant_ids):
    order=sorted(range(len(scores)),key=lambda i:(-float(scores[i]),variant_ids[i]))
    valid=[i for i in order if variant_ids[i] in labels]
    y=[int(labels[variant_ids[i]]) for i in valid];s=[float(scores[i]) for i in valid]
    positives=sum(y);n=len(scores)
    out=dict(scored=n,evaluable=len(valid),positives=positives,coverage=len(valid)/n if n else 0,average_precision=float(average_precision_score(y,s)) if positives else None,roc_auc=float(roc_auc_score(y,s)) if positives and positives<len(y) else None,brier=float(brier_score_loss(y,s)) if y else None,ranking_population='all scored variants; missing endpoints not treated as negative')
    for budget in (1,5):
        k=max(1,math.ceil(n*budget/100)) if n else 0;top=order[:k]
        observed=[i for i in top if variant_ids[i] in labels];hits=sum(bool(labels[variant_ids[i]]) for i in observed)
        out[f'budget_{budget}']=dict(selected=k,observed=len(observed),hits=hits,recall=hits/positives if positives else None,precision=hits/len(observed) if observed else None,unknown=k-len(observed))
    return out

def benchmark(origin=None,horizon=1):
    completed=[];skipped=[]
    with connect() as conn:
        max_r=conn.execute('SELECT max(release_id) r FROM release').fetchone()['r']
        if not max_r:return dict(runs=[],skipped=['Import releases first'])
        origins=[origin] if origin else list(range(2,max_r+1))
        cache={}
        def get(o,fs):
            key=(o,fs)
            if key not in cache:cache[key]=features(conn,o,fs)
            return cache[key]
        for t in origins:
            if not 1<=t<=max_r:raise ValueError('Unknown origin release')
            source=conn.execute('SELECT manifest_sha256 FROM release WHERE release_id<=%s ORDER BY release_id',(t,)).fetchall()
            lineage=digest(source)
            labels={r['variant_id']:r['realized_label'] for r in conn.execute('SELECT * FROM prediction_outcome WHERE origin_release_id=%s AND horizon=%s',(t,horizon)).fetchall()}
            current=get(t,'static');ids=sorted(current)
            if not ids:continue
            configs=[('no_change','static'),('conflict','static'),('submitter_count','static'),('recency','temporal'),('logistic','static'),('logistic','temporal'),('boosted','static'),('boosted','temporal')]
            for method,fs in configs:
                keys=STATIC+(TEMPORAL if fs=='temporal' else [])
                train_x=[];train_y=[];latest_training_origin=None
                if method in ('logistic','boosted'):
                    for u in range(1,t-horizon+1):
                        old=get(u,fs)
                        resolved=conn.execute('SELECT variant_id,realized_label FROM prediction_outcome WHERE origin_release_id=%s AND horizon=%s AND target_release_id<=%s',(u,horizon,t)).fetchall()
                        for row in resolved:
                            if row['variant_id'] in old:
                                train_x.append([old[row['variant_id']][k] for k in keys]);train_y.append(int(row['realized_label']));latest_training_origin=u
                    if len(train_x)<10 or len(set(train_y))<2:
                        skipped.append(dict(origin=t,method=method,feature_set=fs,reason='Insufficient mature training examples or only one outcome class'));continue
                cf=get(t,fs);x=[[cf[i][k] for k in keys] for i in ids]
                if method=='no_change':scores=np.zeros(len(ids))
                elif method=='conflict':scores=np.array([cf[i]['class_C'] for i in ids],dtype=float)
                elif method=='submitter_count':
                    vals=np.array([cf[i]['submitters'] for i in ids]);scores=vals/max(1,float(vals.max()))
                elif method=='recency':scores=np.array([1/(1+cf[i]['releases_since_submission']) for i in ids],dtype=float)
                else:
                    model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=600,random_state=42)) if method=='logistic' else HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,random_state=42)
                    model.fit(np.array(train_x),np.array(train_y));scores=model.predict_proba(np.array(x))[:,1]
                rk=digest(dict(method=method,fs=fs,origin=t,horizon=horizon,lineage=lineage,features=keys,implementation=digest(open(__file__).read())))
                existing=conn.execute('SELECT model_id FROM model_version WHERE run_key=%s',(rk,)).fetchone()
                if existing:mid=existing['model_id']
                else:
                    meta=dict(code_hash=digest(open(__file__).read()),dataset_hash=lineage,feature_names=keys,train_rows=len(train_x),train_positives=sum(train_y),latest_training_origin=latest_training_origin,training_label_cutoff=t,seed=42,target='reconstructed-group-change',aggregation_policy='highest-review-known-group-v1',validation_status='See official-match report; reconstructed benchmark, not clinical truth')
                    mid=conn.execute('INSERT INTO model_version(model_name,feature_set,origin_release_id,horizon,trained_on_release,run_key,metadata) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING model_id',(method,fs,t,horizon,t if train_x else None,rk,Jsonb(meta))).fetchone()['model_id']
                    order=sorted(range(len(ids)),key=lambda i:(-float(scores[i]),ids[i]))
                    with conn.cursor() as cur:cur.executemany('INSERT INTO drift_prediction(model_id,variant_id,origin_release_id,horizon,score,audit_rank) VALUES(%s,%s,%s,%s,%s,%s)',[(mid,ids[i],t,horizon,float(scores[i]),rank) for rank,i in enumerate(order,1)])
                    if train_x:
                        from backend.db import ROOT
                        import joblib
                        path=ROOT/'artifacts/models';path.mkdir(parents=True,exist_ok=True);joblib.dump(model,path/f'{rk}.joblib')
                    enqueue(conn,f'model:{rk}','model',dict(model_id=mid))
                result=metric_values(scores,labels,ids)
                conn.execute('INSERT INTO benchmark_result VALUES(%s,%s,now()) ON CONFLICT(model_id) DO UPDATE SET metrics=EXCLUDED.metrics,created_at=now()',(mid,Jsonb(result)))
                completed.append(dict(model_id=mid,origin=t,method=method,feature_set=fs,metrics=result))
    return dict(runs=completed,skipped=skipped,warning='Small cohort benchmark; model improvement is not assumed. Origin feature history is partial and history_length is explicit.')
