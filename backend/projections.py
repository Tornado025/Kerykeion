"""Replayable PostgreSQL outbox consumers; independent delivery acknowledgements."""
import json,os
from pathlib import Path
from pymongo import MongoClient,ReplaceOne
from neo4j import GraphDatabase
from backend.db import connect,ROOT

DATASET=os.getenv('KERYKEION_DATASET') or json.loads((ROOT/'config/project.json').read_text())['dataset']

def release_snapshot(c,rid):
    versions=c.execute('''SELECT v.*,a.variant_id,a.submitter_id,s.submitter_name,g.gene_symbol,x.gene_id,x.variant_name FROM assertion_version v JOIN clinical_assertion a USING(scv_accession) JOIN submitter s USING(submitter_id) JOIN variant x USING(variant_id) JOIN gene g USING(gene_id) WHERE v.first_release_id<=%s''',(rid,)).fetchall()
    events=c.execute('SELECT e.*,r.label FROM event_details e JOIN release r ON r.release_id=e.to_release_id WHERE e.to_release_id=%s',(rid,)).fetchall()
    return versions,events

def mongo_consume(db,c,event):
    if event['topic']=='release':
        rid=event['payload']['release_id'];versions,events=release_snapshot(c,rid)
        operations=[]
        for row in versions:
            doc=json.loads(json.dumps(row,default=str));doc['dataset']=DATASET;doc['_id']=f"{DATASET}:{doc['scv_accession']}:{doc['version_no']}"
            operations.append(ReplaceOne({'_id':doc['_id']},doc,upsert=True))
        if operations:db.scv_evidence.bulk_write(operations,ordered=False)
        release=c.execute('SELECT * FROM release WHERE release_id=%s',(rid,)).fetchone();release=json.loads(json.dumps(release,default=str));release['_id']=f'{DATASET}:{rid}';db.etl_runs.replace_one({'_id':release['_id']},release,upsert=True)
    elif event['topic']=='model':
        mid=event['payload']['model_id'];model=c.execute('SELECT * FROM model_version WHERE model_id=%s',(mid,)).fetchone()
        rows=c.execute('SELECT * FROM feature_materialization WHERE origin_release_id=%s AND feature_set=%s',(model['origin_release_id'],model['feature_set'])).fetchall()
        ops=[]
        for row in rows:
            doc=dict(row);doc['_id']=f"{DATASET}:{row['variant_id']}:{row['origin_release_id']}:{row['feature_set']}";doc['dataset']=DATASET
            ops.append(ReplaceOne({'_id':doc['_id']},doc,upsert=True))
        db.feature_vectors.create_index([('dataset',1),('origin_release_id',1),('feature_set',1)])
        # The relational vectors are immutable: write one copy per origin/input set,
        # not another copy for each method and horizon using those same inputs.
        stored=db.feature_vectors.count_documents({'dataset':DATASET,'origin_release_id':model['origin_release_id'],'feature_set':model['feature_set']})
        if ops and stored!=len(rows):db.feature_vectors.bulk_write(ops,ordered=False)
        # One immutable context per fitted run, joined to the already stored
        # variant/origin feature vector. Do not duplicate the same input values
        # (or a redundant pointer) for millions of prediction rows.
        doc=dict(_id=f'{DATASET}:model:{mid}',dataset=DATASET,model_id=mid,
                 method='observed_feature_context',origin_release_id=model['origin_release_id'],
                 feature_set=model['feature_set'],feature_names=model['metadata'].get('feature_names',[]),
                 feature_vector_key=f"{DATASET}:{{variant_id}}:{model['origin_release_id']}:{model['feature_set']}",
                 note='Join this run context to its variant/origin feature vector. Inputs are not causal explanations or SHAP attributions.')
        db.prediction_explanations.replace_one({'_id':doc['_id']},doc,upsert=True)

def graph_consume(session,c,event):
    if event['topic']!='release':return
    rid=event['payload']['release_id'];versions,events=release_snapshot(c,rid)
    # Query current authoritative intervals even on an old replay; cannot reopen a newer closed episode.
    for start in range(0,len(versions),500):
        batch=[json.loads(json.dumps(v,default=str)) for v in versions[start:start+500]]
        session.run('''UNWIND $rows AS row
        MERGE (g:Gene {dataset:$dataset,id:row.gene_id}) SET g.symbol=row.gene_symbol
        MERGE (v:Variant {dataset:$dataset,id:row.variant_id}) SET v.name=row.variant_name
        MERGE (v)-[:IN_GENE]->(g)
        MERGE (s:Submitter {dataset:$dataset,id:row.submitter_id}) SET s.name=row.submitter_name
        MERGE (s)-[a:ASSERTED {episode:row.scv_accession+':'+toString(row.version_no)}]->(v)
        SET a.scv=row.scv_accession,a.version=row.version_no,a.class_code=row.class_code,a.from_release=row.first_release_id,a.to_release=row.last_release_id,a.date_evaluated=row.date_evaluated''',rows=batch,dataset=DATASET).consume()
    if events:
        session.run('''UNWIND $rows AS row MATCH (v:Variant {dataset:$dataset,id:row.variant_id})
        MERGE (r:Release {dataset:$dataset,id:row.to_release_id}) SET r.label=row.label
        MERGE (v)-[e:CHANGED {event_id:row.event_id}]->(r) SET e.from_class=row.from_class,e.to_class=row.to_class,e.type=row.change_type,e.at_release=row.to_release_id''',rows=[dict(x) for x in events],dataset=DATASET).consume()

def replay(limit=100):
    result=dict(processed=0,mongo=0,neo4j=0,errors=[])
    mongo=None;graph=None
    try:
        mongo=MongoClient(os.getenv('MONGO_URI','mongodb://localhost:27018'),serverSelectionTimeoutMS=2000);mongo.admin.command('ping')
    except Exception as e:result['errors'].append('MongoDB: '+type(e).__name__);mongo=None
    try:
        graph=GraphDatabase.driver(os.getenv('NEO4J_URI','bolt://localhost:17688'),auth=(os.getenv('NEO4J_USER','neo4j'),os.getenv('NEO4J_PASSWORD','local-demo-only')),connection_timeout=3);graph.verify_connectivity()
        with graph.session() as session:
            for label in ('Gene','Variant','Submitter','Release'):session.run(f'CREATE CONSTRAINT {label.lower()}_identity IF NOT EXISTS FOR (n:{label}) REQUIRE (n.dataset,n.id) IS UNIQUE').consume()
    except Exception as e:result['errors'].append('Neo4j: '+type(e).__name__);graph=None
    try:
        with connect() as c:
            if not c.execute('SELECT pg_try_advisory_lock(720251102) ok').fetchone()['ok']:return dict(processed=0,errors=['Another replay worker is running'])
            events=c.execute('SELECT * FROM outbox_event WHERE NOT delivered_mongo OR NOT delivered_neo4j ORDER BY event_id LIMIT %s',(limit,)).fetchall()
            for event in events:
                error=[]
                if mongo is not None and not event['delivered_mongo']:
                    try:
                        mongo_consume(mongo[os.getenv('MONGO_DB','kerykeion')],c,event)
                        c.execute('UPDATE outbox_event SET delivered_mongo=true WHERE event_id=%s',(event['event_id'],));result['mongo']+=1
                    except Exception as e:error.append('MongoDB '+type(e).__name__+': '+str(e)[:250])
                if graph is not None and not event['delivered_neo4j']:
                    try:
                        with graph.session() as session:graph_consume(session,c,event)
                        c.execute('UPDATE outbox_event SET delivered_neo4j=true WHERE event_id=%s',(event['event_id'],));result['neo4j']+=1
                    except Exception as e:error.append('Neo4j '+type(e).__name__+': '+str(e)[:250])
                c.execute('UPDATE outbox_event SET attempts=attempts+1,last_error=%s WHERE event_id=%s',('; '.join(error) or None,event['event_id']))
                c.commit();result['processed']+=1;result['errors'].extend(error)
    finally:
        if mongo is not None:mongo.close()
        if graph is not None:graph.close()
    return result
