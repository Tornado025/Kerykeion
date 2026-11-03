import os
from backend.db import connect
from backend.projections import DATASET

def health():
    result={}
    try:
        with connect() as c:
            result['postgres']=dict(status='ready',releases=c.execute('SELECT count(*) n FROM release').fetchone()['n'])
            result['outbox']=c.execute('SELECT count(*) FILTER(WHERE NOT delivered_mongo) mongo_pending,count(*) FILTER(WHERE NOT delivered_neo4j) neo4j_pending FROM outbox_event').fetchone()
    except Exception as e:result['postgres']=dict(status='unavailable',detail=type(e).__name__)
    try:
        from pymongo import MongoClient
        with MongoClient(os.getenv('MONGO_URI','mongodb://localhost:27018'),serverSelectionTimeoutMS=1500) as m:
            m.admin.command('ping');result['mongodb']=dict(status='ready',evidence=m[os.getenv('MONGO_DB','kerykeion')].scv_evidence.count_documents({}))
    except Exception as e:result['mongodb']=dict(status='unavailable',detail=type(e).__name__)
    try:
        from neo4j import GraphDatabase
        with GraphDatabase.driver(os.getenv('NEO4J_URI','bolt://localhost:17688'),auth=(os.getenv('NEO4J_USER','neo4j'),os.getenv('NEO4J_PASSWORD','local-demo-only')),connection_timeout=2) as g:
            g.verify_connectivity();result['neo4j']=dict(status='ready')
    except Exception as e:result['neo4j']=dict(status='unavailable',detail=type(e).__name__)
    return result

def releases():
    with connect() as c:return c.execute('SELECT * FROM release ORDER BY release_id').fetchall()

def selected_release(c,rid=None):
    r=c.execute('SELECT * FROM release WHERE release_id=%s',(rid,)).fetchone() if rid else c.execute('SELECT * FROM release ORDER BY release_id DESC LIMIT 1').fetchone()
    if not r:raise LookupError('No accepted release is available. Import an archive first.')
    return r

def genes(rid=None):
    with connect() as c:
        if not c.execute('SELECT 1 FROM release LIMIT 1').fetchone():
            return dict(release=None,genes=c.execute('SELECT g.*,0 AS variants,0 AS changed FROM gene g ORDER BY gene_symbol').fetchall())
        r=selected_release(c,rid)
        rows=c.execute("""SELECT g.*,count(s.variant_id) AS variants,count(e.event_id) FILTER(WHERE e.change_type='semantic') AS changed
        FROM gene g LEFT JOIN variant v USING(gene_id) LEFT JOIN variant_state s ON s.variant_id=v.variant_id AND s.release_id=%s
        LEFT JOIN change_event e ON e.variant_id=s.variant_id AND e.to_release_id=%s GROUP BY g.gene_id ORDER BY g.gene_symbol""",(r['release_id'],r['release_id'])).fetchall()
        return dict(release=r,genes=rows)

def variants(symbol,rid=None,search='',classification='',limit=80,offset=0):
    with connect() as c:
        r=selected_release(c,rid)
        clauses=['s.release_id=%s','g.gene_symbol=%s'];args=[r['release_id'],symbol.upper()]
        if search:clauses.append('(v.variant_name ILIKE %s OR v.variant_id::text=%s)');args.extend(['%'+search+'%',search])
        if classification:clauses.append('s.aggregate_class=%s');args.append(classification)
        where=' AND '.join(clauses)
        count=c.execute(f'SELECT count(*) n FROM variant v JOIN gene g USING(gene_id) JOIN variant_state s USING(variant_id) WHERE {where}',args).fetchone()['n']
        rows=c.execute(f'''SELECT v.*,s.*,g.gene_symbol,e.change_type,e.from_class,e.to_class FROM variant v JOIN gene g USING(gene_id)
        JOIN variant_state s USING(variant_id) LEFT JOIN event_details e ON e.variant_id=v.variant_id AND e.to_release_id=s.release_id
        WHERE {where} ORDER BY (e.change_type='semantic') DESC NULLS LAST,v.variant_id LIMIT %s OFFSET %s''',args+[limit,offset]).fetchall()
        return dict(release=r,variants=rows,total=count,limit=limit,offset=offset)

def variant_detail(vid,rid=None):
    with connect() as c:
        r=selected_release(c,rid)
        v=c.execute('SELECT v.*,g.gene_symbol,g.description FROM variant v JOIN gene g USING(gene_id) WHERE variant_id=%s',(vid,)).fetchone()
        if not v:raise LookupError('Variant not found in the imported cohort.')
        assertions=c.execute('''SELECT a.scv_accession,a.submitter_id,u.submitter_name,v.version_no,v.class_code,v.date_evaluated,v.first_release_id,v.last_release_id,r.status_label,r.review_stars FROM clinical_assertion a
          JOIN submitter u USING(submitter_id) JOIN assertion_version v USING(scv_accession) JOIN review_status r USING(status_code)
          WHERE a.variant_id=%s AND int4range(v.first_release_id,v.last_release_id,'[)') @> %s::integer ORDER BY r.review_stars DESC,a.scv_accession''',(vid,r['release_id'])).fetchall()
        # The selected historical view never returns future states, events, or scores.
        states=c.execute('SELECT s.*,r.label FROM variant_state s JOIN release r USING(release_id) WHERE variant_id=%s AND release_id<=%s ORDER BY release_id',(vid,r['release_id'])).fetchall()
        events=c.execute('SELECT e.*,r.label FROM event_details e JOIN release r ON e.to_release_id=r.release_id WHERE variant_id=%s AND to_release_id<=%s ORDER BY to_release_id',(vid,r['release_id'])).fetchall()
        predictions=c.execute('''SELECT p.*,m.model_name,m.feature_set FROM prediction_results p JOIN model_version m USING(model_id) WHERE p.variant_id=%s AND p.origin_release_id<=%s ORDER BY p.origin_release_id DESC,m.model_id''',(vid,r['release_id'])).fetchall()
        for p in predictions:
            if p['target_release_id'] and p['target_release_id']>r['release_id']:p['realized_label']=None;p['target_release_id']=None
        validation=c.execute('SELECT * FROM validation_result WHERE variant_id=%s AND release_id=%s',(vid,r['release_id'])).fetchone()
        return dict(variant=v,release=r,assertions=assertions,states=states,events=events,predictions=predictions,validation=validation)

def changes(rid=None,limit=100):
    with connect() as c:
        r=selected_release(c,rid)
        return dict(release=r,events=c.execute('SELECT e.*,v.variant_name,g.gene_symbol FROM event_details e JOIN variant v USING(variant_id) JOIN gene g USING(gene_id) WHERE to_release_id=%s ORDER BY change_type,variant_id LIMIT %s',(r['release_id'],limit)).fetchall())

def models():
    with connect() as c:return c.execute('SELECT m.*,r.label,b.metrics FROM model_version m JOIN release r ON r.release_id=m.origin_release_id LEFT JOIN benchmark_result b USING(model_id) ORDER BY m.origin_release_id DESC,m.model_id').fetchall()

def audit_queue(model_id=None,limit=100,budget=5,classification="",gene=""):
    with connect() as c:
        if model_id is None:
            row=c.execute('SELECT model_id FROM model_version ORDER BY origin_release_id DESC,model_id DESC LIMIT 1').fetchone()
            if not row:return dict(model=None,predictions=[],total=0,budget_count=0)
            model_id=row['model_id']
        model=c.execute('SELECT m.*,r.label FROM model_version m JOIN release r ON r.release_id=m.origin_release_id WHERE model_id=%s',(model_id,)).fetchone()
        if not model:raise LookupError('Model run not found.')
        where='p.model_id=%s'
        args=[model_id]
        if classification:where+=' AND s.aggregate_class=%s';args.append(classification)
        if gene:where+=' AND g.gene_symbol=%s';args.append(gene.upper())
        source='FROM prediction_results p JOIN variant v USING(variant_id) JOIN gene g USING(gene_id) JOIN variant_state s ON s.variant_id=p.variant_id AND s.release_id=p.origin_release_id'
        n=c.execute(f'SELECT count(*) n {source} WHERE {where}',args).fetchone()['n']
        import math
        k=max(1,math.ceil(n*budget/100)) if n else 0
        rows=c.execute(f"""SELECT p.*,v.variant_name,g.gene_symbol,s.aggregate_class,
          row_number() OVER(ORDER BY p.audit_rank) AS review_rank
          {source} WHERE {where} ORDER BY p.audit_rank LIMIT %s""",args+[min(k,limit)]).fetchall()
        return dict(model=model,predictions=rows,total=n,budget_count=k)

def provenance(vid,rid=None):
    with connect() as c: rid=selected_release(c,rid)["release_id"]
    from neo4j import GraphDatabase
    with GraphDatabase.driver(os.getenv('NEO4J_URI','bolt://localhost:17688'),auth=(os.getenv('NEO4J_USER','neo4j'),os.getenv('NEO4J_PASSWORD','local-demo-only'))) as d:
        with d.session() as s:
            return s.run('MATCH (s:Submitter)-[a:ASSERTED]->(v:Variant {id:$id,dataset:$dataset}) WHERE a.from_release<=$release RETURN s.name AS submitter,a.scv AS accession,a.version AS version,a.class_code AS classification,a.from_release AS first_release,CASE WHEN a.to_release<=$release THEN a.to_release ELSE null END AS last_release ORDER BY accession,version LIMIT 100',id=vid,release=rid,dataset=DATASET).data()


def evidence(scv,rid=None):
    from pymongo import MongoClient
    with connect() as c:
        rid=selected_release(c,rid)['release_id']
        version=c.execute("SELECT version_no FROM assertion_version WHERE scv_accession=%s AND int4range(first_release_id,last_release_id,'[)') @> %s::integer",(scv,rid)).fetchone()
        if not version:raise LookupError('No visible assertion version at this release.')
    with MongoClient(os.getenv('MONGO_URI','mongodb://localhost:27018'),serverSelectionTimeoutMS=2000) as client:
        doc=client[os.getenv('MONGO_DB','kerykeion')].scv_evidence.find_one({'scv_accession':scv,'version_no':version['version_no'],'dataset':DATASET},{'_id':0})
        if not doc:raise LookupError('Evidence projection is pending for this assertion version.')
        return {'source':'MongoDB historical evidence projection','scv_accession':scv,'version_no':version['version_no'],'raw':doc.get('raw',{})}
