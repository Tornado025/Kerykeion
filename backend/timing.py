"""Landmark discrete-time models for the NEXT observed change, with censoring.

Each observed variant/month starts a new landmark. Follow-up stops at its first
change, first missing archive observation, six months or the knowledge cutoff.
No endpoint reversal can erase a first event. No censor is labelled a future zero.
"""
import hashlib,json,math
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score
from psycopg.types.json import Jsonb
from backend.db import ROOT,connect
from backend.ml import STATIC,TEMPORAL

MAX_MONTHS=6
BASE=STATIC+TEMPORAL
EXTRA=['pathogenic_share','uncertain_share','benign_share','change_density','assertions_per_submitter','log_assertions','log_submitters']
KEYS=BASE+EXTRA+['months_ahead']
CACHE=ROOT/'artifacts/timing';CACHE.mkdir(parents=True,exist_ok=True)


def followup(states,origin,cutoff,limit=MAX_MONTHS):
    """states: variants x releases; -1 means not observed. Return duration/event."""
    n=len(states);duration=np.zeros(n,dtype=np.int16);event=np.zeros(n,dtype=bool)
    active=states[:,origin]>=0
    initial=states[:,origin]
    for step in range(1,min(limit,cutoff-origin)+1):
        active &= states[:,origin+step]>=0
        duration[active]=step
        changed=active & (states[:,origin+step]!=initial)
        event[changed]=True
        active &= ~changed
    return duration,event


def curve(hazards):
    survival=np.cumprod(1-np.clip(hazards,0,1),axis=1)
    mass=np.concatenate([np.ones((len(hazards),1)),survival[:,:-1]],axis=1)*hazards
    return mass,1-survival


def concordance(duration,event,risk):
    good=0.;pairs=0
    for i in np.flatnonzero(event):
        later=duration>duration[i]
        diff=risk[i]-risk[later]
        good+=float((diff>0).sum())+.5*float((diff==0).sum());pairs+=int(later.sum())
    return good/pairs if pairs else None


def censor_survival(duration,event):
    """Discrete KM: G[k] = P(follow-up lasts at least month k).

    A censor at month k has a KNOWN no-event status through month k. Its loss
    of follow-up affects month k+1, never the already observed month k.
    """
    g=np.ones(MAX_MONTHS+1)
    for k in range(1,MAX_MONTHS+1):
        at_risk=int((duration>=k-1).sum())
        censored=int(((duration==k-1)&~event).sum())
        g[k]=g[k-1]*(1-censored/at_risk) if at_risk else 0
    return g


def timing_metrics(duration,event,cumulative):
    # IPCW uses the held-out landmark's censoring distribution, solely for
    # evaluation. Never used for fitting/calibration. Report every horizon's
    # observed coverage; do not evaluate beyond administrative follow-up.
    g=censor_survival(duration,event);metrics=[]
    maximum=min(MAX_MONTHS,int(duration.max(initial=0)))
    for k in range(1,maximum+1):
        occurred=event & (duration<=k)
        survived=(duration>=k)&~occurred
        known=occurred|survived
        if g[k]<=1e-9:continue
        w=np.zeros(len(duration));w[survived]=1/g[k]
        for t in range(1,k+1):w[event&(duration==t)]=1/max(g[t],1e-9)
        error=(occurred.astype(float)-cumulative[:,k-1])**2
        observed=error[known].mean() if known.any() else None
        y=occurred[known].astype(int);scores=cumulative[known,k-1]
        count=max(1,math.ceil(.05*len(duration)))
        top=np.argsort(-cumulative[:,k-1],kind='stable')[:count]
        hits=int(occurred[top].sum());positive=int(occurred.sum())
        metrics.append(dict(months=k,ipcw_brier=float(np.mean(w*error)),observed_status_brier=float(observed) if observed is not None else None,coverage=float(known.mean()),events=positive,average_precision=float(average_precision_score(y,scores)) if y.sum() else None,recall_top5=hits/positive if positive else None,precision_top5=hits/int(known[top].sum()) if known[top].sum() else None))
    # Conditional mean time is explicitly evaluated only on observed events.
    mass=np.diff(np.column_stack([np.zeros(len(cumulative)),cumulative]),axis=1)
    conditional=(mass*np.arange(1,MAX_MONTHS+1)).sum(axis=1)/np.maximum(cumulative[:,-1],1e-12)
    return dict(population=len(duration),observed_events=int(event.sum()),censored=int((~event).sum()),concordance=concordance(duration,event,cumulative[:,-1]),integrated_brier=float(np.mean([r['ipcw_brier'] for r in metrics])) if metrics else None,event_only_timing_mae_months=float(np.abs(conditional[event]-duration[event]).mean()) if event.any() else None,horizons=metrics,warning='Timing MAE conditions on observed events. C-index omits tied event times. IPCW assumes non-informative censoring; administrative follow-up limits the evaluated horizon.')


class Dataset:
    def __init__(self):
        with connect() as c:
            self.releases=c.execute('SELECT release_id,label,manifest_sha256 FROM release ORDER BY release_id').fetchall()
            self.last=self.releases[-1]['release_id'];self.ids=np.array([r['variant_id'] for r in c.execute('SELECT variant_id FROM variant ORDER BY variant_id')],dtype=np.int64)
            self.lookup={int(v):i for i,v in enumerate(self.ids)}
            self.states=np.full((len(self.ids),self.last+1),-1,dtype=np.int8)
            for r in c.execute('SELECT variant_id,release_id,aggregate_class FROM variant_state'):
                self.states[self.lookup[r['variant_id']],r['release_id']]='PVBCO'.index(r['aggregate_class'])
        self.matrices={}

    def inputs(self,origin):
        if origin in self.matrices:return self.matrices[origin]
        path=CACHE/f'inputs-{origin}.npz'
        source=self.releases[origin-1]['manifest_sha256']
        if path.exists():
            saved=np.load(path)
            if str(saved['source'])==source:
                result=(saved['ids'],saved['x']);self.matrices[origin]=result;return result
        with connect() as c:
            rows=c.execute("SELECT variant_id,features FROM feature_materialization WHERE origin_release_id=%s AND feature_set='temporal' ORDER BY variant_id",(origin,)).fetchall()
        if not rows:raise ValueError(f'Historical input vectors missing at origin {origin}')
        ids=np.array([r['variant_id'] for r in rows],dtype=np.int64)
        x=np.empty((len(rows),len(KEYS)-1),dtype=np.float32)
        for i,r in enumerate(rows):
            f=r['features'];count=max(1,f['assertions'])
            derived=[f['n_p']/count,f['n_vus']/count,f['n_b']/count,f['past_changes']/max(1,f['history_length']-1),f['assertions']/max(1,f['submitters']),np.log1p(f['assertions']),np.log1p(f['submitters'])]
            x[i]=[f[k] for k in BASE]+derived
        np.savez_compressed(path,ids=ids,x=x,source=source)
        self.matrices[origin]=(ids,x);return ids,x

    def truth(self,origin,cutoff,ids):
        indices=np.array([self.lookup[int(v)] for v in ids])
        return followup(self.states[indices],origin,cutoff)

    def person_period(self,origins,cutoff,seed=42):
        rng=np.random.default_rng(seed);xs=[];ys=[];weights=[]
        event_count=0;exposures=0
        # All events; probability sample of no-event exposure months. Inverse
        # sampling weights preserve the natural event rate (no balanced classes).
        probability=.025
        for origin in origins:
            ids,x=self.inputs(origin);duration,event=self.truth(origin,cutoff,ids)
            for step in range(1,min(MAX_MONTHS,cutoff-origin)+1):
                risk=duration>=step;y=event&(duration==step)
                keep=risk&(y|(rng.random(len(x))<probability))
                if not keep.any():continue
                xs.append(np.column_stack([x[keep],np.full(keep.sum(),step)]));ys.append(y[keep])
                weights.append(np.where(y[keep],1.,1/probability))
                event_count+=int(y.sum());exposures+=int(risk.sum())
        if not xs:raise ValueError('No observable future exposure months at training cutoff')
        return np.concatenate(xs),np.concatenate(ys).astype(int),np.concatenate(weights),dict(events=event_count,exposures=exposures,negative_sampling_probability=probability)


class HazardModel:
    def __init__(self,name):self.name=name;self.calibrator=None;self.scaler=None

    def fit(self,data,cutoff):
        fit_end=cutoff-3
        if fit_end<3:raise ValueError('Need historical fit and later calibration periods')
        x,y,w,counts=data.person_period(range(1,fit_end),fit_end)
        self.metadata=dict(fit_label_cutoff=fit_end,calibration_label_cutoff=cutoff,calibration_origins=list(range(fit_end,cutoff)),sample_rows=len(y),**counts)
        normal=w*len(w)/w.sum()
        if self.name in ('constant_hazard','class_hazard'):
            x,y,w,counts=data.person_period(range(1,cutoff),cutoff)
            self.metadata.update(fit_label_cutoff=cutoff,calibration_origins=[],calibration='none',sample_rows=len(y),**counts)
            self.rates={};global_rate=float(np.average(y,weights=w))
            self.global_rate=global_rate
            for cls in range(5):
                take=x[:,cls]==1
                numerator=float((w[take]*y[take]).sum())+500*global_rate
                self.rates[cls]=numerator/(float(w[take].sum())+500)
            return self
        if self.name=='logistic_hazard':
            self.scaler=StandardScaler().fit(x,sample_weight=normal)
            self.model=LogisticRegression(C=.05,max_iter=400,random_state=42)
            self.model.fit(self.scaler.transform(x),y,sample_weight=normal)
        else:
            self.model=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,min_samples_leaf=150,l2_regularization=30,learning_rate=.05,early_stopping=False,random_state=42)
            self.model.fit(x,y,sample_weight=normal)
        del x,y,w,normal
        cx,cy,cw,calcounts=data.person_period(range(fit_end,cutoff),cutoff,seed=43)
        raw=self.raw(cx);logit=np.log(np.clip(raw,1e-7,1-1e-7)/(1-np.clip(raw,1e-7,1-1e-7)))[:,None]
        self.calibrator=LogisticRegression(C=100,max_iter=300,random_state=42)
        self.calibrator.fit(logit,cy,sample_weight=cw*len(cw)/cw.sum())
        self.metadata.update(calibration_events=calcounts['events'],calibration_exposures=calcounts['exposures'],calibration='past-only weighted sigmoid')
        return self

    def raw(self,x):
        return self.model.predict_proba(self.scaler.transform(x) if self.scaler else x)[:,1]

    def predict(self,x):
        if self.name=='constant_hazard':return np.full((len(x),MAX_MONTHS),self.global_rate)
        if self.name=='class_hazard':
            rates=np.array([self.rates[int(np.argmax(r[:5]))] for r in x])
            return np.repeat(rates[:,None],MAX_MONTHS,axis=1)
        hazards=[]
        for step in range(1,MAX_MONTHS+1):
            raw=self.raw(np.column_stack([x,np.full(len(x),step)]))
            logit=np.log(np.clip(raw,1e-7,1-1e-7)/(1-np.clip(raw,1e-7,1-1e-7)))[:,None]
            hazards.append(self.calibrator.predict_proba(logit)[:,1])
        return np.column_stack(hazards)


def save_forecast(data,origin,model,metrics,selection):
    ids,x=data.inputs(origin);mass,cumulative=curve(model.predict(x))
    metadata=dict(target='first-observed-group-change-v1',source_cutoff=origin,max_months=MAX_MONTHS,features=KEYS,selection=selection,**model.metadata)
    sources=[r['manifest_sha256'] for r in data.releases if r['release_id']<=origin]
    key=hashlib.sha256(json.dumps(dict(method=model.name,origin=origin,sources=sources,metadata=metadata,code=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),sort_keys=True).encode()).hexdigest()
    artifact=CACHE/f'{key}.joblib';joblib.dump(model,artifact)
    metadata.update(artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),artifact_path=str(artifact.relative_to(ROOT)))
    with connect() as c:
        row=c.execute('INSERT INTO timing_run(run_key,origin_release_id,method,max_months,metadata,metrics) VALUES(%s,%s,%s,6,%s,%s) ON CONFLICT(run_key) DO UPDATE SET metrics=EXCLUDED.metrics RETURNING run_id',(key,origin,model.name,Jsonb(metadata),Jsonb(metrics))).fetchone()
        rid=row['run_id']
        if not c.execute('SELECT 1 FROM timing_forecast WHERE run_id=%s LIMIT 1',(rid,)).fetchone():
            order=np.lexsort((ids,-cumulative[:,2]))
            with c.cursor() as cur:
                with cur.copy('COPY timing_forecast FROM STDIN') as copy:
                    for rank,i in enumerate(order,1):
                        median=int(np.argmax(cumulative[i]>=.5)+1) if cumulative[i,-1]>=.5 else None
                        conditional=float(np.dot(mass[i],np.arange(1,7))/max(cumulative[i,-1],1e-12))
                        copy.write_row((rid,int(ids[i]),Jsonb(mass[i].tolist()),Jsonb(cumulative[i].tolist()),conditional,median,rank))
    return rid
