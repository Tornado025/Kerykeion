import gzip
import hashlib
import json
from collections import Counter
from psycopg.types.json import Jsonb
from backend.db import connect

def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def enqueue(conn,key,topic,payload):
    conn.execute('INSERT INTO outbox_event(event_key,topic,payload) VALUES(%s,%s,%s) ON CONFLICT(event_key) DO NOTHING',(key,topic,Jsonb(payload)))

def aggregate(conn,rid):
    conn.execute('''WITH live AS (
      SELECT a.variant_id,a.submitter_id,v.class_code,r.review_stars
      FROM clinical_assertion a JOIN assertion_version v USING(scv_accession) JOIN review_status r USING(status_code)
      WHERE int4range(v.first_release_id,v.last_release_id,'[)') @> %s::integer
    ), best AS (SELECT variant_id,max(review_stars) AS stars FROM live WHERE class_code<>'O' GROUP BY variant_id),
    chosen AS (SELECT l.variant_id,CASE WHEN count(DISTINCT class_code)=1 THEN min(class_code) ELSE 'C' END AS cls
      FROM live l JOIN best b ON l.variant_id=b.variant_id AND l.review_stars=b.stars WHERE l.class_code<>'O' GROUP BY l.variant_id),
    counts AS (SELECT variant_id,count(DISTINCT submitter_id) AS ns,count(*) AS na,
      count(*) FILTER(WHERE class_code='P') AS np,count(*) FILTER(WHERE class_code='V') AS nv,count(*) FILTER(WHERE class_code='B') AS nb FROM live GROUP BY variant_id)
    INSERT INTO variant_state SELECT t.variant_id,%s,coalesce(ch.cls,'O'),coalesce(b.stars,0),coalesce(c.ns,0),coalesce(c.na,0),coalesce(c.np,0),coalesce(c.nv,0),coalesce(c.nb,0)
      FROM import_variant_ids t LEFT JOIN chosen ch USING(variant_id) LEFT JOIN best b USING(variant_id) LEFT JOIN counts c USING(variant_id)''',(rid,rid))
    if rid>1:
        conn.execute('''INSERT INTO change_event(variant_id,from_release_id,to_release_id,change_type)
        SELECT n.variant_id,p.release_id,n.release_id,CASE WHEN p.aggregate_class<>n.aggregate_class THEN 'semantic' ELSE 'review_only' END
        FROM variant_state n JOIN variant_state p ON n.variant_id=p.variant_id AND p.release_id=%s
        WHERE n.release_id=%s AND (p.aggregate_class<>n.aggregate_class OR p.review_stars<>n.review_stars)''',(rid-1,rid))

def mature_outcomes(conn):
    # Labels are model-independent and only created for observed endpoint pairs.
    conn.execute('''INSERT INTO prediction_outcome(variant_id,origin_release_id,horizon,target_release_id,realized_label)
    SELECT a.variant_id,a.release_id,h.h,b.release_id,(a.aggregate_class<>b.aggregate_class)
    FROM variant_state a CROSS JOIN (VALUES (1),(3)) h(h)
    JOIN variant_state b ON b.variant_id=a.variant_id AND b.release_id=a.release_id+h.h
    ON CONFLICT DO NOTHING''')

def import_document(doc):
    manifest = digest(doc)
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(720251101)')
        previous=conn.execute('SELECT * FROM release ORDER BY release_id DESC LIMIT 1').fetchone()
        existing=conn.execute('SELECT * FROM release WHERE label=%s',(doc['label'],)).fetchone()
        if existing:
            if existing['manifest_sha256'] != manifest: raise ValueError('Published release differs from input: create a new dataset instead of overwriting history')
            return dict(status='unchanged',release_id=existing['release_id'],label=doc['label'])
        if previous and (str(previous['release_date'])>=doc['release_date'] or previous['provenance']!=doc['provenance']):
            raise ValueError('Imports must be chronological and cannot mix real archives with synthetic fixtures')
        rid=(previous['release_id']+1) if previous else 1
        conn.execute('INSERT INTO release(release_id,release_date,label,manifest_sha256,provenance) VALUES(%s,%s,%s,%s,%s)',(rid,doc['release_date'],doc['label'],manifest,doc['provenance']))
        conn.execute('CREATE TEMP TABLE import_variant_ids(variant_id bigint PRIMARY KEY) ON COMMIT DROP')
        with conn.cursor() as cur:
            cur.executemany('INSERT INTO variant(variant_id,gene_id,variant_name,variant_type,chromosome,position,ref,alt) VALUES(%(variant_id)s,%(gene_id)s,%(variant_name)s,%(variant_type)s,%(chromosome)s,%(position)s,%(ref)s,%(alt)s) ON CONFLICT(variant_id) DO NOTHING',doc['variants'])
            cur.executemany('INSERT INTO import_variant_ids VALUES(%s)',[(v['variant_id'],) for v in doc['variants']])
        seen={}; duplicates=0; submitters={}; reviews={}; new_assertions=[]; closures=[]; versions=[]
        owners={r['scv_accession']:r for r in conn.execute('SELECT scv_accession,variant_id,submitter_id FROM clinical_assertion').fetchall()}
        latest={r['scv_accession']:r for r in conn.execute('SELECT DISTINCT ON(scv_accession) scv_accession,version_no,content_hash,last_release_id FROM assertion_version ORDER BY scv_accession,version_no DESC').fetchall()}
        for a in doc['assertions']:
            identity=a['scv_accession'];h=digest({k:a[k] for k in ('variant_id','submitter_id','class_code','review_status','date_evaluated')})
            if identity in seen:
                if seen[identity]!=h:raise ValueError(f'Conflicting duplicate assertion in one release: {identity}')
                duplicates+=1;continue
            seen[identity]=h;submitters[a['submitter_id']]=a['submitter_name'];reviews[a['review_status']]=a['review_stars']
            owner=owners.get(identity)
            if owner and (owner['variant_id']!=a['variant_id'] or owner['submitter_id']!=a['submitter_id']):raise ValueError(f'Assertion identity mapping changed: {identity}')
            if not owner:new_assertions.append((identity,a['variant_id'],a['submitter_id'],rid))
            current=latest.get(identity)
            if current and current['last_release_id'] is None and current['content_hash']==h:continue
            if current and current['last_release_id'] is None:closures.append((rid,identity,current['version_no']))
            versions.append((identity,(current['version_no']+1) if current else 1,a['class_code'],a['review_status'],a['date_evaluated'],rid,h,Jsonb(a.get('raw',{}))))
        with conn.cursor() as cur:
            cur.executemany('INSERT INTO submitter(submitter_id,submitter_name) VALUES(%s,%s) ON CONFLICT DO NOTHING',list(submitters.items()))
            cur.executemany('INSERT INTO review_status VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',[(v,v,n) for v,n in reviews.items()])
            cur.executemany('INSERT INTO clinical_assertion VALUES(%s,%s,%s,%s)',new_assertions)
            cur.executemany('UPDATE assertion_version SET last_release_id=%s WHERE scv_accession=%s AND version_no=%s',closures)
            cur.executemany('INSERT INTO assertion_version VALUES(%s,%s,%s,%s,%s,%s,NULL,%s,%s)',versions)
        if not seen: raise ValueError('No assertions: refusing to publish an incomplete release')
        conn.execute('UPDATE assertion_version SET last_release_id=%s WHERE last_release_id IS NULL AND NOT (scv_accession=ANY(%s))',(rid,list(seen)))
        aggregate(conn,rid)
        for vid,official in doc['official'].items():
            conn.execute('''INSERT INTO validation_result SELECT variant_id,release_id,%s,aggregate_class,aggregate_class=%s FROM variant_state WHERE variant_id=%s AND release_id=%s''',(official,official,int(vid),rid))
        for artifact in doc.get('artifacts',[]):
            conn.execute('INSERT INTO release_artifact VALUES(%s,%s,%s,%s,%s)',(rid,artifact['kind'],artifact['url'],artifact['sha256'],artifact['bytes']))
        stats=conn.execute('''SELECT count(*) AS variants,count(*) FILTER(WHERE matches) AS matched,count(*) FILTER(WHERE NOT matches) AS mismatched FROM validation_result WHERE release_id=%s''',(rid,)).fetchone()
        stats.update(assertions=len(seen),duplicate_rows=duplicates,rejected=doc.get('rejected',0),policy='highest-review-known-group-v1',adapter=doc.get('adapter_version','fixture'))
        conn.execute('UPDATE release SET stats=%s WHERE release_id=%s',(Jsonb(stats),rid))
        mature_outcomes(conn)
        enqueue(conn,f'release:{rid}:{manifest}','release',dict(release_id=rid))
        return dict(status='imported',release_id=rid,label=doc['label'],stats=stats)

def import_file(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt') as f:return import_document(json.load(f))
