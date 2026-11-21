"""Reproduce all monthly one/three-release runs and deliver projections."""
import json,os,time
from backend.db import ROOT,connect,migrate
from backend.ml import benchmark
from backend.projections import replay


def progress(state):
    state['updated_at']=time.time()
    path=ROOT/'artifacts/model-progress.json'
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,default=str));temp.replace(path)
    print(json.dumps(state,default=str),flush=True)


def main():
    migrate()
    for horizon in (1,3):
        report=benchmark(horizon=horizon,progress=progress)
        (ROOT/f'artifacts/benchmark-h{horizon}.json').write_text(json.dumps(report,default=str))
    progress(dict(phase='projecting'))
    while True:
        with connect() as c:
            pending=c.execute('SELECT count(*) n FROM outbox_event WHERE NOT delivered_mongo OR NOT delivered_neo4j').fetchone()['n']
        if not pending:break
        result=replay(limit=8)
        progress(dict(phase='projecting',pending=pending,result=result))
        if result['errors']:raise RuntimeError(result['errors'])
    progress(dict(phase='complete'))


if __name__=='__main__':main()
