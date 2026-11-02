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
    finally:
        mongo.drop_database(namespace);mongo.close()
        with graph.session() as s:s.run('MATCH (n {dataset:$dataset}) DETACH DELETE n',dataset=namespace).consume()
        graph.close()
