"""Resume selected monthly archives; publish and project each before proceeding.

Models are deliberately excluded. Stop on errors to avoid silent history gaps.
"""
import argparse
import fcntl
import json
import time
import traceback
from backend.db import ROOT, migrate
from backend.projections import replay
from etl.archive import fetch_month
from etl.importer import import_file


def main():
    p = argparse.ArgumentParser()
    p.add_argument('months', nargs='+')
    args = p.parse_args()
    if args.months != sorted(set(args.months)):
        p.error('Supply unique months in chronological order')
    progress = ROOT / 'artifacts/backfill-progress.json'
    progress.parent.mkdir(exist_ok=True)

    def update(phase, month, **extra):
        state = dict(phase=phase, month=month, months=args.months,
                     updated_at=time.time(), **extra)
        temp = progress.with_suffix('.tmp')
        temp.write_text(json.dumps(state, default=str, indent=2))
        temp.replace(progress)
        print(json.dumps(state, default=str), flush=True)

    migrate()
    month = args.months[0]
    try:
        for month in args.months:
            update('fetching', month)
            extract = fetch_month(month)
            update('importing', month)
            result = import_file(extract)
            update('projecting', month, result=result)
            projections = replay()
            if projections.get('errors'):
                raise RuntimeError(f'Projection failed: {projections["errors"]}')
            update('ready', month, result=result, projections=projections)
        update('complete', month)
    except Exception as exc:
        update('failed', month, error=str(exc))
        traceback.print_exc()
        raise


if __name__ == '__main__':
    lock_path = ROOT / 'artifacts/backfill.lock'
    lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('An archive backfill is already running.')
        main()
