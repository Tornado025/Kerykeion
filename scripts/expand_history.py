"""Build a chronological research history without rewriting the demo schema.

No training or projections: this is a separate PostgreSQL research corpus, not
an application release. Durable extracts are shared; imported rows are isolated.
"""
import argparse,fcntl,json,os,re,time,traceback
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from backend.db import ROOT,connect,migrate
from etl.archive import fetch_month
from etl.importer import import_file


def months_between(start,end):
    for value in (start,end):
        if not re.fullmatch(r'20[0-9]{2}-(0[1-9]|1[0-2])',value):
            raise ValueError('Dates must be YYYY-MM')
    a=int(start[:4])*12+int(start[5:])-1;b=int(end[:4])*12+int(end[5:])-1
    if a>b:raise ValueError('Start must not be after end')
    return [f'{n//12:04}-{n%12+1:02}' for n in range(a,b+1)]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--start',default='2023-01');parser.add_argument('--end',default='2026-11')
    parser.add_argument('--schema',default='research_history_2023_v1');args=parser.parse_args()
    if not re.fullmatch(r'research_[a-z0-9_]+',args.schema):parser.error('Use a research_ schema name')
    months=months_between(args.start,args.end)
    base=os.getenv('DATABASE_URL','postgresql://kerykeion:local-demo-only@localhost:55433/kerykeion')
    with psycopg.connect(base,autocommit=True) as c:
        c.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(args.schema)))
    os.environ['DATABASE_URL']=make_conninfo(base,options=f'-c search_path={args.schema}')
    os.environ.setdefault('KERYKEION_DOWNLOAD_WORKERS','2')
    out=ROOT/'artifacts/history-expansion';out.mkdir(parents=True,exist_ok=True)
    def update(phase,month=None,**extra):
        value=dict(phase=phase,month=month,schema=args.schema,expected_months=len(months),start=args.start,end=args.end,updated_at=time.time(),**extra)
        temp=out/'progress.tmp';temp.write_text(json.dumps(value,indent=2,default=str));temp.replace(out/'progress.json');print(json.dumps(value,default=str),flush=True)
    try:
        migrate()
        with connect() as c:
            labels=[r['label'] for r in c.execute('SELECT label FROM release ORDER BY release_id')]
        if labels!=months[:len(labels)]:raise ValueError('Research history is not a prefix of the requested month sequence')
        for month in months:
            update('fetching',month);extract=fetch_month(month)
            update('importing',month);result=import_file(extract)
            with connect() as c:
                loaded=c.execute('SELECT count(*) n FROM release').fetchone()['n']
            update('imported',month,loaded=loaded,result=result)
        with connect() as c:
            releases=c.execute('SELECT release_id,label FROM release ORDER BY release_id').fetchall()
            assert [r['label'] for r in releases]==months
            artifacts=c.execute('SELECT count(*) n FROM release_artifact').fetchone()['n'];assert artifacts==2*len(months)
            counts={table:c.execute(sql.SQL('SELECT count(*) n FROM {}').format(sql.Identifier(table))).fetchone()['n'] for table in ('variant','variant_state','assertion_version','change_event')}
            genes=c.execute('SELECT g.gene_symbol,count(*) AS variants FROM variant v JOIN gene g USING(gene_id) GROUP BY g.gene_symbol ORDER BY g.gene_symbol').fetchall()
        from scripts.history_coverage import coverage_report
        coverage=coverage_report(args.schema)
        report=dict(coverage_file='artifacts/history-expansion/coverage.json',releases=releases,source_artifacts=artifacts,counts=counts,genes=genes,schema=args.schema,projections='Not created: isolated research corpus; demo projections remain unchanged',models='Not trained')
        (out/'verification.json').write_text(json.dumps(report,indent=2,default=str));update('complete',months[-1],loaded=len(months),verification=report)
    except Exception as exc:
        update('failed',error=str(exc));traceback.print_exc();raise

if __name__=='__main__':
    folder=ROOT/'artifacts/history-expansion';folder.mkdir(parents=True,exist_ok=True)
    with (folder/'worker.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('A historical expansion worker is already running')
        main()
