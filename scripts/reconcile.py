"""Replay the authoritative outbox after rebuilding a local projection."""
import argparse
from backend.db import connect
from backend.projections import replay

def main():
    p=argparse.ArgumentParser();p.add_argument('--consumer',choices=['mongo','neo4j','both'],required=True);a=p.parse_args()
    with connect() as c:
        if a.consumer in ('mongo','both'):c.execute('UPDATE outbox_event SET delivered_mongo=false')
        if a.consumer in ('neo4j','both'):c.execute('UPDATE outbox_event SET delivered_neo4j=false')
    result=replay(limit=10000);print(result)
    if result['errors']:raise SystemExit(1)
if __name__=='__main__':main()
