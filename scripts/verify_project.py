"""Read-only final acceptance audit of the local three-store dataset."""
import hashlib,json,os,time,statistics
from pathlib import Path
import requests
from pymongo import MongoClient
from neo4j import GraphDatabase
from backend.db import ROOT,connect
from backend.projections import DATASET
from backend.services import health


def main():
    expected=[f'{y}-{m:02}' for y in (2025,2026) for m in range(1,13) if (y,m)<=(2026,11)]
    with connect() as c:
        releases=c.execute('SELECT release_id,label,stats FROM release ORDER BY release_id').fetchall()
        assert [r['label'] for r in releases]==expected
        artifacts=c.execute('SELECT * FROM release_artifact').fetchall();assert len(artifacts)==46
        assert all(len(r['sha256'])==64 and r['bytes']>0 for r in artifacts)
        assert not c.execute('SELECT 1 FROM feature_materialization WHERE lineage_max_release>origin_release_id LIMIT 1').fetchone()
        runs=c.execute('SELECT * FROM model_version').fetchall()
        for m in runs:
            latest=m['metadata'].get('latest_training_origin')
            assert latest is None or latest+m['horizon']<=m['origin_release_id']
            path=m['metadata'].get('artifact_path')
            if path:assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==m['metadata']['artifact_sha256']
        counts={t:c.execute(f'SELECT count(*) n FROM {t}').fetchone()['n'] for t in ('assertion_version','change_event','variant_state','model_version','drift_prediction','feature_materialization')}
        for row in c.execute('SELECT m.model_id,count(p.prediction_id) n,(SELECT count(*) FROM variant_state WHERE release_id=m.origin_release_id) expected FROM model_version m LEFT JOIN drift_prediction p USING(model_id) GROUP BY m.model_id'):
            assert row['n']==row['expected'],row
    status=health();assert all(status[k]['status']=='ready' for k in ('postgres','mongodb','neo4j'))
    assert status['outbox']==dict(mongo_pending=0,neo4j_pending=0)
    with MongoClient(os.getenv('MONGO_URI','mongodb://localhost:27018')) as mongo:
        db=mongo[os.getenv('MONGO_DB','kerykeion')]
        assert db.scv_evidence.count_documents({'dataset':DATASET})==counts['assertion_version']
        vector_count=db.feature_vectors.count_documents({'dataset':DATASET})
        assert vector_count==counts['feature_materialization']
    with GraphDatabase.driver(os.getenv('NEO4J_URI','bolt://localhost:17688'),auth=(os.getenv('NEO4J_USER','neo4j'),os.getenv('NEO4J_PASSWORD','local-demo-only'))) as driver:
        with driver.session() as session:
            edges=session.run('MATCH (s:Submitter {dataset:$d})-[a:ASSERTED]->(:Variant {dataset:$d}) RETURN count(a) AS n',d=DATASET).single()['n']
            assert edges==counts['assertion_version']
            events=session.run('MATCH (:Variant {dataset:$d})-[a:CHANGED]->(:Release {dataset:$d}) RETURN count(a) AS n',d=DATASET).single()['n']
            assert events==counts['change_event']
    timings={}
    for path in ['/api/releases','/api/genes?release=23','/api/variants/188342?release=2','/api/audit-queue?budget=1&classification=B&gene=BRCA1','/api/experiments/summary']:
        values=[]
        for _ in range(11):
            start=time.perf_counter();response=requests.get('http://127.0.0.1:8001'+path,timeout=60);response.raise_for_status();values.append((time.perf_counter()-start)*1000)
        timings[path]=dict(first_request_ms=values[0],warm_p50_ms=statistics.median(values[1:]),warm_p95_ms=sorted(values[1:])[9],repetitions=10)
    report=dict(passed=True,releases=23,source_artifacts=46,counts=counts,services=status,mongo_feature_vectors=vector_count,neo4j_episodes=edges,neo4j_changes=events,api_timings=timings)
    (ROOT/'artifacts/final-acceptance.json').write_text(json.dumps(report,indent=2,default=str));print(json.dumps(report,default=str))

if __name__=='__main__':main()
