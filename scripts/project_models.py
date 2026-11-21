"""Drain pending projections without refitting completed model runs."""
import json
from backend.db import connect
from backend.projections import replay
from scripts.finish_models import progress


def main():
    while True:
        with connect() as c:
            pending=c.execute('SELECT count(*) n FROM outbox_event WHERE NOT delivered_mongo OR NOT delivered_neo4j').fetchone()['n']
        if not pending:break
        result=replay(limit=8)
        progress(dict(phase='projecting',pending=pending,result=result))
        if result['errors']:raise RuntimeError(result['errors'])
    progress(dict(phase='complete'))

if __name__=='__main__':main()
