import csv,io,os,secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,HTTPException,Query,Header
from fastapi.responses import FileResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from backend.db import ROOT
from backend import services

app=FastAPI(title='Kerykeion',version='0.1.0')

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
@app.get('/api/models')
def models():return services.models()
@app.get('/api/audit-queue')
def queue(model:int|None=Query(None,ge=1),limit:int=Query(100,ge=1,le=1000),budget:int=Query(5,ge=1,le=100),classification:str=Query("",pattern="^[PVBCO]?$"),gene:str=Query("",pattern="^(BRCA1|BRCA2|TP53)?$")):
    return services.audit_queue(model,limit,budget,classification,gene)
@app.get('/api/audit-queue.csv')
def queue_csv(model:int=Query(ge=1),budget:int=Query(5,ge=1,le=100),classification:str=Query("",pattern="^[PVBCO]?$"),gene:str=Query("",pattern="^(BRCA1|BRCA2|TP53)?$")):
    result=services.audit_queue(model,100000,budget,classification,gene)
    out=io.StringIO();w=csv.writer(out);w.writerow(['rank','variant_id','gene','score','origin_release','horizon','realized_label'])
    for p in result['predictions']:w.writerow([p['review_rank'],p['variant_id'],p['gene_symbol'],p['score'],p['origin_release_id'],p['horizon'],p['realized_label']])
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
    return FileResponse(DIST/'index.html')
@app.get('/{page}.html')
def page(page:str):
    if page not in ('gene','variant','audit','benchmark','releases'):raise HTTPException(404)
    return home()
