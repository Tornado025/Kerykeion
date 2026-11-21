"""Describe the isolated research corpus; never silently substitute demo data."""
import argparse,csv,json,os,re
import psycopg
from psycopg.conninfo import make_conninfo
from backend.db import ROOT,connect


def coverage_report(schema):
    if not re.fullmatch(r'research_[a-z0-9_]+',schema):raise ValueError('Use a research_ schema')
    base=os.getenv('DATABASE_URL','postgresql://kerykeion:local-demo-only@localhost:55433/kerykeion')
    previous=os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL']=make_conninfo(base,options=f'-c search_path={schema}')
    try:
        with connect() as c:
            monthly=c.execute('''SELECT r.label,r.release_id,count(s.variant_id) AS variants,
                count(s.variant_id) FILTER(WHERE s.aggregate_class='V') AS uncertain_variants,
                (SELECT count(*) FROM change_event e WHERE e.to_release_id=r.release_id AND e.change_type='semantic') AS group_changes,
                (SELECT count(*) FROM validation_result v WHERE v.release_id=r.release_id AND NOT v.matches) AS official_group_mismatches,
                (SELECT count(*) FROM release_artifact a WHERE a.release_id=r.release_id) AS source_artifacts
                FROM release r LEFT JOIN variant_state s USING(release_id) GROUP BY r.release_id ORDER BY r.release_id''').fetchall()
            genes=c.execute('''SELECT g.gene_symbol,count(DISTINCT v.variant_id) AS variants,
                count(DISTINCT e.variant_id) AS variants_with_observed_group_change,count(e.event_id) AS observed_group_changes
                FROM gene g JOIN variant v USING(gene_id)
                LEFT JOIN change_event e ON e.variant_id=v.variant_id AND e.change_type='semantic'
                GROUP BY g.gene_symbol ORDER BY g.gene_symbol''').fetchall()
            gaps=c.execute('''WITH obs AS (SELECT variant_id,release_id,lag(release_id) OVER(PARTITION BY variant_id ORDER BY release_id) AS previous FROM variant_state)
                SELECT count(*) AS reappearance_gaps,count(DISTINCT variant_id) AS variants_with_reappearance_gap FROM obs WHERE release_id>previous+1''').fetchone()
            artifacts=c.execute('SELECT release_id,kind,url,sha256,bytes FROM release_artifact ORDER BY release_id,kind').fetchall()
    finally:
        if previous is None:os.environ.pop('DATABASE_URL',None)
        else:os.environ['DATABASE_URL']=previous
    report=dict(schema=schema,monthly=monthly,genes=genes,gaps=gaps,source_artifacts=artifacts,
        warning='Descriptive corpus counts, not model performance. Group changes exclude review-only changes. Repeated forecasting landmarks are not independent events.')
    out=ROOT/'artifacts/history-expansion';out.mkdir(exist_ok=True,parents=True)
    (out/'coverage.json').write_text(json.dumps(report,indent=2,default=str))
    for name,rows in [('monthly',monthly),('genes',genes)]:
        if rows:
            with (out/f'{name}.csv').open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--schema',default='research_history_2023_v1');args=parser.parse_args()
    result=coverage_report(args.schema);print(json.dumps(dict(months=len(result['monthly']),genes=result['genes'],gaps=result['gaps']),default=str))
