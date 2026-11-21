import copy,json,os,uuid
import pytest
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from etl.archive import group,stars,date_value
from etl.fixtures import documents
from etl.importer import import_document
from backend.db import connect,migrate
from backend.ml import features,metric_values
from backend.services import variant_detail

@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED','false') # Existing research/API tests run independently of account tests.
    if os.getenv('RUN_DB_TESTS')!='1':pytest.skip('Set RUN_DB_TESTS=1 for isolated PostgreSQL integration tests')
    base=os.getenv('DATABASE_URL','postgresql://kerykeion:local-demo-only@localhost:55433/kerykeion')
    schema='test_'+uuid.uuid4().hex
    with psycopg.connect(base,autocommit=True) as c:c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    monkeypatch.setenv('DATABASE_URL',make_conninfo(base,options=f'-c search_path={schema}'))
    migrate()
    try:yield
    finally:
        with psycopg.connect(base,autocommit=True) as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

def test_class_mapping():
    assert group('Conflicting classifications of pathogenicity')=='C'
    assert group('Pathogenic/Likely pathogenic')=='P'
    assert group('Benign/Likely benign')=='B'
    assert group('Uncertain significance')=='V'
    assert group('risk factor')=='O'
    assert stars('no assertion criteria provided')==0
    assert stars('reviewed by expert panel')==3
    assert date_value('Jan 02, 2025')=='2025-01-02'
    assert date_value('-') is None

def test_queue_missing_endpoints_and_ties():
    m=metric_values([.8,.8,.1],{10:True,30:False},[20,10,30])
    assert m['budget_5']['hits']==1 # equal score: ID 10 precedes 20
    assert m['evaluable']==2 and m['positives']==1
    assert metric_values([0],{},[1])['average_precision'] is None

def test_idempotency_and_published_immutability(database):
    doc=next(documents());first=import_document(doc)
    assert first['status']=='imported' and import_document(doc)['status']=='unchanged'
    changed=copy.deepcopy(doc);changed['official']['100']='B'
    with pytest.raises(ValueError,match='Published release differs'):import_document(changed)
    with connect() as c:
        assert c.execute('SELECT count(*) n FROM release').fetchone()['n']==1
        assert c.execute('SELECT count(*) n FROM assertion_version').fetchone()['n']==40

def test_history_does_not_expose_future(database):
    docs=list(documents());import_document(docs[0]);import_document(docs[1]);import_document(docs[2])
    old=variant_detail(100,1)
    assert len(old['states'])==1 and old['events']==[]
    assert all(a['first_release_id']<=1 for a in old['assertions'])
    with connect() as c:
        assert c.execute('SELECT count(*) n FROM change_event').fetchone()['n']>0
        assert c.execute('SELECT count(*) n FROM event_details WHERE from_class<>to_class').fetchone()['n']>0

def test_disappearance_and_reappearance(database):
    docs=list(documents());scv=docs[0]['assertions'][0]['scv_accession'];import_document(docs[0])
    docs[1]['assertions']=[a for a in docs[1]['assertions'] if a['scv_accession']!=scv];import_document(docs[1]);import_document(docs[2])
    with connect() as c:
        rows=c.execute('SELECT first_release_id,last_release_id FROM assertion_version WHERE scv_accession=%s ORDER BY version_no',(scv,)).fetchall()
        assert rows[0]['last_release_id']==2 and rows[-1]['first_release_id']==3
        assert not c.execute("SELECT 1 FROM assertion_version WHERE scv_accession=%s AND int4range(first_release_id,last_release_id,'[)') @> 2",(scv,)).fetchone()

def test_feature_invariance_after_future_import(database):
    docs=list(documents());import_document(docs[0]);import_document(docs[1])
    with connect() as c:before=features(c,2,'temporal')
    import_document(docs[2])
    with connect() as c:
        assert features(c,2,'temporal')==before
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("INSERT INTO feature_materialization VALUES(100,1,'future','{}',3,'bad')")

def test_overlap_constraint(database):
    import_document(next(documents()))
    with connect() as c:
        with pytest.raises(psycopg.errors.ExclusionViolation):
            c.execute('''INSERT INTO assertion_version SELECT scv_accession,99,class_code,status_code,date_evaluated,first_release_id,last_release_id,content_hash,raw FROM assertion_version LIMIT 1''')

def test_horizon_three_endpoint_not_intermediate_change(database):
    docs=list(documents())
    for i in range(4):
        for a in docs[i]['assertions']:a['class_code']='P' if i==1 else 'V'
        docs[i]['official']={str(v['variant_id']):('P' if i==1 else 'V') for v in docs[i]['variants']}
        import_document(docs[i])
    with connect() as c:
        assert c.execute('SELECT realized_label FROM prediction_outcome WHERE variant_id=100 AND origin_release_id=1 AND horizon=3').fetchone()['realized_label'] is False

def test_api_and_model_pipeline(database):
    from backend.ml import benchmark
    from backend.app import app
    from fastapi.testclient import TestClient
    for d in documents():import_document(d)
    result=benchmark(4,1);assert result['runs']
    with TestClient(app) as client:
        assert client.get('/api/releases').status_code==200
        assert client.get('/api/variants/100?release=1').json()['events']==[]
        assert client.get('/api/genes/BRCA1/variants?limit=2').json()['limit']==2
        assert client.get('/api/variants/999999').status_code==404
        assert client.get('/api/genes/BRCA1/variants?limit=10000').status_code==422
        assert client.post('/api/projections/replay').status_code==403
        assert client.get('/api/audit-queue.csv?model=1').status_code==200
        all_rows=client.get('/api/audit-queue?model=1&budget=100').json()['predictions']
        page=client.get('/api/audit-queue?model=1&budget=100&limit=2&offset=2').json()['predictions']
        assert [r['variant_id'] for r in page]==[r['variant_id'] for r in all_rows[2:4]]
        assert page[0]['review_rank']==3
        assert client.get('/api/audit-queue?offset=-1').status_code==422
        filtered=client.get('/api/audit-queue?model=1&gene=BRCA1&classification=P&budget=1').json()
        assert filtered['total']>0 and filtered['budget_count']==1
        assert len(filtered['predictions'])==1
        assert filtered['predictions'][0]['aggregate_class']=='P'
        assert filtered['predictions'][0]['gene_symbol']=='BRCA1'
        assert filtered['predictions'][0]['review_rank']==1
        csv_result=client.get('/api/audit-queue.csv?model=1&gene=BRCA1&classification=P&budget=1')
        assert len(csv_result.text.strip().splitlines())==2
        assert client.get('/api/audit-queue?classification=bad').status_code==422


def test_archive_header_after_comment_preamble(tmp_path):
    import gzip
    from etl.archive import archive_rows
    path=tmp_path/'submission.txt.gz'
    with gzip.open(path,'wt') as f:f.write('##Overview of submitted interpretations\n\n#VariationID: identifier description\n#VariationID\tClinicalSignificance\tSCV\n2\tPathogenic\tSCV00002.3\n')
    assert list(archive_rows(path))==[{'VariationID':'2','ClinicalSignificance':'Pathogenic','SCV':'SCV00002.3'}]

def test_projection_partial_retry_and_idempotency(database,monkeypatch):
    if os.getenv('RUN_PROJECTION_TESTS')!='1':pytest.skip('Set RUN_PROJECTION_TESTS=1 with MongoDB and Neo4j running')
    from pymongo import MongoClient
    from neo4j import GraphDatabase
    from backend import projections,services
    namespace='test_'+uuid.uuid4().hex
    monkeypatch.setattr(projections,'DATASET',namespace);monkeypatch.setattr(services,'DATASET',namespace);monkeypatch.setenv('MONGO_DB',namespace)
    mongo=MongoClient(os.getenv('MONGO_URI','mongodb://localhost:27018'))
    graph=GraphDatabase.driver(os.getenv('NEO4J_URI','bolt://localhost:17688'),auth=(os.getenv('NEO4J_USER','neo4j'),os.getenv('NEO4J_PASSWORD','local-demo-only')))
    original=projections.graph_consume
    try:
        import_document(next(documents()))
        def unavailable(*args):raise ConnectionError('simulated failure after independent MongoDB delivery')
        monkeypatch.setattr(projections,'graph_consume',unavailable)
        first=projections.replay();assert first['mongo']==1 and first['errors']
        assert mongo[namespace].scv_evidence.count_documents({})==40
        with connect() as c:
            row=c.execute('SELECT delivered_mongo,delivered_neo4j FROM outbox_event').fetchone()
            assert row==dict(delivered_mongo=True,delivered_neo4j=False)
        monkeypatch.setattr(projections,'graph_consume',original)
        retried=projections.replay();assert retried['mongo']==0 and retried['neo4j']==1 and not retried['errors']
        assert projections.replay()['processed']==0
        assert mongo[namespace].scv_evidence.count_documents({})==40
        assert services.evidence('SCVFIX100A',1)['raw']['fixture'] is True
        assert len(services.provenance(100,1))==2
        from backend.ml import benchmark
        benchmark(1,1)
        projected=projections.replay()
        assert not projected['errors']
        assert mongo[namespace].feature_vectors.count_documents({})==40
        assert mongo[namespace].prediction_explanations.count_documents({})==4
        assert projections.replay()['processed']==0
        with connect() as c:pid=c.execute('SELECT prediction_id FROM drift_prediction LIMIT 1').fetchone()['prediction_id']
        assert services.prediction_context(pid)['source']=='MongoDB verified archived feature snapshot'

    finally:
        mongo.drop_database(namespace);mongo.close()
        with graph.session() as s:s.run('MATCH (n {dataset:$dataset}) DETACH DELETE n',dataset=namespace).consume()
        graph.close()

def test_submitter_alias_requires_consistent_scv_ownership():
    from etl.importer import resolve_submitter_aliases
    owner={'SCV1':dict(variant_id=1,submitter_id='name:old')}
    rows=[dict(scv_accession='SCV1',variant_id=1,submitter_id='name:new',submitter_name='Renamed lab'),
          dict(scv_accession='SCV2',variant_id=2,submitter_id='name:new',submitter_name='Renamed lab')]
    aliases,_=resolve_submitter_aliases(rows,owner,{})
    assert aliases=={'name:new':'name:old'}
    with pytest.raises(ValueError,match='Ambiguous'):
        resolve_submitter_aliases(rows,owner,{'name:new':'name:other'})
    with pytest.raises(ValueError,match='variant mapping'):
        resolve_submitter_aliases([dict(rows[0],variant_id=99)],owner,{})
    with pytest.raises(ValueError,match='identity mapping'):
        resolve_submitter_aliases([dict(rows[0],submitter_id='123')],owner,{})


def test_renamed_submitter_keeps_identity_and_historical_evidence(database):
    docs=list(documents())
    for a in docs[0]['assertions']:
        if a['submitter_id']=='A':a['submitter_id']='name:old'
    for a in docs[1]['assertions']:
        if a['submitter_id']=='A':
            a['submitter_id']='name:new';a['submitter_name']='Renamed lab';a['raw']={'Submitter':'Renamed lab'}
    import_document(docs[0]);import_document(docs[1])
    with connect() as c:
        alias=c.execute('SELECT * FROM submitter_alias').fetchone()
        assert alias['submitter_id']=='name:old'
        assert not c.execute("SELECT 1 FROM submitter WHERE submitter_id='name:new'").fetchone()
        assert c.execute("SELECT 1 FROM assertion_version WHERE raw->>'Submitter'='Renamed lab'").fetchone()

def test_archive_large_evidence_field_is_preserved(tmp_path):
    import csv,gzip
    from etl.archive import archive_rows
    path=tmp_path/'large-evidence.txt.gz'
    evidence='Clinical evidence\n'+('x'*150000)
    with gzip.open(path,'wt',newline='') as f:
        writer=csv.writer(f,delimiter='\t')
        writer.writerow(['#VariationID','Description'])
        writer.writerow(['123',evidence])
    previous=csv.field_size_limit()
    try:
        csv.field_size_limit(131072)
        rows=list(archive_rows(path))
        assert rows==[{'VariationID':'123','Description':evidence}]
    finally:
        csv.field_size_limit(previous)

def test_training_runs_are_resumable_and_horizon_cutoffs_hold(database):
    from backend.ml import benchmark
    from backend.services import models,prediction_context,model_manifest
    for d in documents():import_document(d)
    first=benchmark(5,3)
    assert first['runs']
    with connect() as c:
        before=c.execute('SELECT count(*) n FROM drift_prediction').fetchone()['n']
    second=benchmark(5,3)
    assert {r['model_id'] for r in first['runs']}=={r['model_id'] for r in second['runs']}
    with connect() as c:
        assert c.execute('SELECT count(*) n FROM drift_prediction').fetchone()['n']==before
        for row in c.execute('SELECT * FROM model_version'):
            cutoff=row['metadata'].get('latest_training_origin')
            assert cutoff is None or cutoff+row['horizon']<=row['origin_release_id']
        pid=c.execute('SELECT prediction_id FROM drift_prediction LIMIT 1').fetchone()['prediction_id']
    context=prediction_context(pid)
    assert context['features'] and context['feature_hash']
    assert model_manifest(context['model_id'])['horizon']==3

def test_next_change_counts_reversal_and_censors_missing_months():
    import numpy as np
    from backend.timing import followup,curve,timing_metrics
    states=np.array([[-1,0,1,0,0],[-1,0,0,-1,1],[-1,0,0,0,0]])
    duration,event=followup(states,1,4)
    assert duration.tolist()==[1,1,3]
    assert event.tolist()==[True,False,False]
    # The event is absent at an earlier knowledge cutoff, never leaked backward.
    d,e=followup(states,1,1)
    assert d.tolist()==[0,0,0] and not e.any()
    mass,cumulative=curve(np.full((3,6),.1))
    assert np.allclose(mass.sum(axis=1),cumulative[:,-1])
    assert np.all(np.diff(cumulative,axis=1)>=0)
    assert np.allclose(cumulative[:,2],1-.9**3)
    metrics=timing_metrics(duration,event,cumulative)
    assert metrics['observed_events']==1 and metrics['censored']==2
    assert metrics['horizons'][0]['coverage']==1

def test_timing_filters_and_first_event_forecast_api(database):
    from backend.services import timing_queue,variant_timing
    from psycopg.types.json import Jsonb
    for d in documents():import_document(d)
    with connect() as c:
        rid=c.execute("INSERT INTO timing_run(run_key,origin_release_id,method,max_months,metadata,metrics) VALUES('test',2,'boosted_hazard',6,'{}','{}') RETURNING run_id").fetchone()['run_id']
        for i,vid in enumerate([100,101,110],1):
            c.execute('INSERT INTO timing_forecast VALUES(%s,%s,%s,%s,3.0,NULL,%s)',(rid,vid,Jsonb([.01]*6),Jsonb([.01,.02,.03,.04,.05,.06]),i))
    result=timing_queue(2,'BRCA1','',3,100,100)
    assert result['total']==2
    assert {r['variant_id'] for r in result['predictions']}=={100,101}
    page=timing_queue(2,'BRCA1','',3,100,1,1)
    assert [r['variant_id'] for r in page['predictions']]==[101]
    assert page['predictions'][0]['review_rank']==2
    assert timing_queue(2,'BRCA1','',3,1,1,1)['predictions']==[]
    assert variant_timing(110,2)['run_id']==rid
    assert variant_timing(110,1) is None
    from backend.app import app
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        assert client.get('/api/timing/forecasts?origin=2&months=7').status_code==422
        response=client.get('/api/timing/forecasts.csv?origin=2&gene=BRCA1&budget=100')
        assert len(response.text.strip().splitlines())==3
        assert 'conditional_mean_month' in response.text
