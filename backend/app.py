import csv,io,os,secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,HTTPException,Query,Header,Request
from fastapi.responses import FileResponse,StreamingResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from backend.db import ROOT
from backend import services
from backend import auth
import psycopg

app=FastAPI(title='Kerykeion',version='0.1.0')
app.include_router(auth.router)

@app.middleware('http')
async def authentication(request:Request,call_next):
    protected=request.url.path.startswith('/api/') and request.url.path!='/api/health' and not request.url.path.startswith('/api/auth/')
    protected=protected or request.url.path in ('/docs','/redoc','/openapi.json')
    try:
        if auth.enabled():
            if request.url.path.startswith('/api/'):
                auth.check_origin(request)
            if protected:
                # Sync database work belongs in the thread pool, not the event loop.
                from starlette.concurrency import run_in_threadpool
                user=await run_in_threadpool(auth.current_user,request)
                if not user:
                    return JSONResponse({'detail':'Sign in to continue.'},status_code=401,headers={'Cache-Control':'no-store'})
                request.state.user=user
        response=await call_next(request)
        if protected or request.url.path.startswith('/api/auth/'):
            response.headers['Cache-Control']='no-store'
        return response
    except HTTPException as exc:
        return JSONResponse({'detail':exc.detail},status_code=exc.status_code,headers=exc.headers)
    except psycopg.Error:
        return JSONResponse({'detail':'The account database is unavailable. Check the database and run migrations.'},status_code=503,headers={'Cache-Control':'no-store'})

@app.exception_handler(LookupError)
async def missing(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404,content={'detail':str(exc)})

@app.get('/api/health')
def health():return services.health()
@app.get('/api/releases')
def releases():return services.releases()
@app.get('/api/genes')
def genes(release:int|None=Query(None,ge=1)):return services.genes(release)
@app.get('/api/genes/{symbol}/variants')
def variants(symbol:str,release:int|None=Query(None,ge=1),search:str=Query('',max_length=150),classification:str=Query('',pattern='^[PVBCO]?$'),limit:int=Query(80,ge=1,le=200),offset:int=Query(0,ge=0)):
    return services.variants(symbol,release,search,classification,limit,offset)
@app.get('/api/variants/{vid}')
def variant(vid:int,release:int|None=Query(None,ge=1)):return services.variant_detail(vid,release)
@app.get('/api/variants/{vid}/provenance')
def provenance(vid:int,release:int|None=Query(None,ge=1)):
    try:return services.provenance(vid,release)
    except Exception:raise HTTPException(503,'Graph projection unavailable. Check local services and replay the outbox.')
@app.get('/api/assertions/{scv}/evidence')
def evidence(scv:str,release:int|None=Query(None,ge=1)):
    if len(scv)>80:raise HTTPException(422,'Invalid accession')
    try:return services.evidence(scv,release)
    except LookupError:raise
    except Exception:raise HTTPException(503,'Evidence store unavailable. Check MongoDB and outbox status.')
@app.get('/api/changes')
def changes(release:int|None=Query(None,ge=1),limit:int=Query(100,ge=1,le=1000)):return services.changes(release,limit)
@app.get('/api/timing/summary')
def timing_summary():return services.timing_summary()
@app.get('/api/variants/{vid}/timing')
def variant_timing(vid:int,origin:int=Query(ge=1)):return services.variant_timing(vid,origin)
@app.get('/api/timing/runs')
def timing_runs():return services.timing_runs()
@app.get('/api/timing/forecasts')
def timing_forecasts(origin:int|None=Query(None,ge=1),gene:str=Query('',pattern='^(BRCA1|BRCA2|TP53)?$'),classification:str=Query('',pattern='^[PVBCO]?$'),months:int=Query(3,ge=1,le=6),budget:int=Query(1,ge=1,le=100),limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0)):
    return services.timing_queue(origin,gene,classification,months,budget,limit,offset)
@app.get('/api/timing/forecasts.csv')
def timing_csv(origin:int|None=Query(None,ge=1),gene:str=Query('',pattern='^(BRCA1|BRCA2|TP53)?$'),classification:str=Query('',pattern='^[PVBCO]?$'),months:int=Query(3,ge=1,le=6),budget:int=Query(1,ge=1,le=100)):
    result=services.timing_queue(origin,gene,classification,months,budget,100000)
    out=io.StringIO();w=csv.writer(out);w.writerow(['rank','variant_id','gene','starting_month','ranking_horizon_months','change_probability','median_month_if_supported','conditional_mean_month_if_change_within_6','first_event_month_probabilities','cumulative_probabilities','run_id'])
    for row in result['predictions']:w.writerow([row['review_rank'],row['variant_id'],row['gene_symbol'],result['run']['label'],months,row['change_probability'],row['median_month'],row['expected_month_if_change'],row['event_probabilities'],row['cumulative_probabilities'],row['run_id']])
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="next-change-timing.csv"'})
@app.get('/api/models')
def models(compact:bool=False):
    rows=services.models()
    return [{**row,'metadata':{k:v for k,v in (row.get('metadata') or {}).items() if k in ('train_rows','training_rows')}} for row in rows] if compact else rows
@app.get('/api/graph/changes')
def graph_changes(first:int=Query(1,ge=1),last:int=Query(23,ge=1)):
    if first>last:raise HTTPException(422,'First release must not exceed last release')
    return services.graph_drift_counts(first,last)
@app.get('/api/variants/{vid}/revisions-before-change')
def graph_revisions(vid:int,release:int=Query(ge=1)):return services.revisions_before_change(vid,release)
@app.get('/api/models/{model_id}')
def model_manifest(model_id:int):return services.model_manifest(model_id)
@app.get('/api/predictions/{prediction_id}/context')
def prediction_context(prediction_id:int):return services.prediction_context(prediction_id)
@app.get('/api/experiments/summary')
def experiment_summary():return services.experiment_summary()
@app.get('/api/audit-queue')
def queue(model:int|None=Query(None,ge=1),limit:int=Query(100,ge=1,le=1000),budget:int=Query(5,ge=1,le=100),classification:str=Query("",pattern="^[PVBCO]?$"),gene:str=Query("",pattern="^(BRCA1|BRCA2|TP53)?$"),offset:int=Query(0,ge=0)):
    return services.audit_queue(model,limit,budget,classification,gene,offset)
@app.get('/api/audit-queue.csv')
def queue_csv(model:int=Query(ge=1),budget:int=Query(5,ge=1,le=100),classification:str=Query("",pattern="^[PVBCO]?$"),gene:str=Query("",pattern="^(BRCA1|BRCA2|TP53)?$")):
    result=services.audit_queue(model,100000,budget,classification,gene)
    out=io.StringIO();w=csv.writer(out);w.writerow(['rank','variant_id','gene','score','origin_release','horizon','realized_label','current_classification','model_id','run_key','starting_month'])
    for p in result['predictions']:w.writerow([p['review_rank'],p['variant_id'],p['gene_symbol'],p['score'],p['origin_release_id'],p['horizon'],p['realized_label'],p['aggregate_class'],model,result['model']['run_key'],result['model']['label']])
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="audit-queue.csv"'})
@app.post('/api/projections/replay')
def replay(x_write_token:str=Header('')):
    token=os.getenv('WRITE_TOKEN','')
    if not token or not secrets.compare_digest(token,x_write_token):raise HTTPException(403,'Projection replay is available through the local CLI.')
    from backend.projections import replay
    return replay()
DIST=ROOT/'frontend/dist'
if (DIST/'assets').exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
@app.get('/')
def home():
    if not (DIST/'index.html').exists():raise HTTPException(503,'Build the React frontend: cd frontend && npm ci && npm run build')
    return FileResponse(DIST/'index.html',headers={'Cache-Control':'no-cache'})
@app.get('/{page}.html')
def page(page:str):
    if page not in ('gene','variant','audit','benchmark','releases','endpoint-predictions','endpoint-checks'):raise HTTPException(404)
    return home()
