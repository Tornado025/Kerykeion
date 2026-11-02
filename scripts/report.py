"""Capture the actual running dataset, validation and benchmark evidence."""
import json
from backend.db import connect,ROOT
from backend.services import health

def main():
    with connect() as c:
        data={
            'releases':c.execute('SELECT release_id,label,provenance,stats FROM release ORDER BY release_id').fetchall(),
            'genes':c.execute('SELECT g.gene_symbol,count(v.variant_id) variants FROM gene g LEFT JOIN variant v USING(gene_id) GROUP BY g.gene_symbol ORDER BY g.gene_symbol').fetchall(),
            'counts':{t:c.execute(f'SELECT count(*) n FROM {t}').fetchone()['n'] for t in ('assertion_version','variant_state','change_event','model_version','drift_prediction','prediction_outcome')},
            'events':c.execute('SELECT change_type,to_release_id,count(*) n FROM change_event GROUP BY change_type,to_release_id ORDER BY to_release_id,change_type').fetchall(),
            'benchmark':c.execute('SELECT m.model_id,m.model_name,m.feature_set,m.origin_release_id,m.horizon,b.metrics FROM model_version m JOIN benchmark_result b USING(model_id) ORDER BY m.model_id').fetchall(),
            'services':health()
        }
    path=ROOT/'artifacts/verification-report.json';path.write_text(json.dumps(data,default=str,indent=2));print(path)
if __name__=='__main__':main()
