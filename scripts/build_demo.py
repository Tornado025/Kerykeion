"""Publish verified selected extracts in order, then score and project each release."""
import argparse,json,time,traceback
from pathlib import Path
from backend.db import ROOT,migrate
from etl.importer import import_file
from backend.ml import benchmark
from backend.projections import replay

def main():
    p=argparse.ArgumentParser();p.add_argument('months',nargs='+');p.add_argument('--wait',action='store_true');p.add_argument('--skip-models',action='store_true');a=p.parse_args()
    migrate();progress=ROOT/'artifacts/demo-progress.json';progress.parent.mkdir(exist_ok=True)
    def update(phase,month,**extra):
        doc=dict(phase=phase,month=month,updated_at=time.time(),**extra);progress.write_text(json.dumps(doc,default=str));print(json.dumps(doc,default=str),flush=True)
    for month in a.months:
        file=ROOT/'data/extracts'/f'{month}.json.gz'
        while not file.exists():
            if not a.wait:raise FileNotFoundError(file)
            update('waiting_for_selected_extract',month);time.sleep(20)
        update('importing',month)
        result=import_file(file);update('published',month,result=result)
        rid=result['release_id']
        if not a.skip_models:
            update('scoring',month)
            # Refresh all origins after a new endpoint matures. Existing runs are idempotent.
            report=benchmark(horizon=1)
            (ROOT/'artifacts/benchmark-latest.json').write_text(json.dumps(report,default=str))
            update('scored',month,runs=len(report['runs']),skipped=report['skipped'])
        update('projecting',month);projection=replay();update('ready',month,projection=projection)
    update('complete',a.months[-1])
if __name__=='__main__':main()
