import argparse,json
from backend.db import migrate

def main():
    p=argparse.ArgumentParser(prog='python -m backend.cli');sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('migrate')
    imp=sub.add_parser('import');imp.add_argument('paths',nargs='+')
    f=sub.add_parser('fetch');f.add_argument('months',nargs='+')
    t=sub.add_parser('train');t.add_argument('--origin',type=int);t.add_argument('--horizon',type=int,choices=(1,3),default=1)
    sub.add_parser('project');sub.add_parser('health');sub.add_parser('demo-fixture')
    a=p.parse_args()
    if a.cmd=='migrate':migrate();print('Migrations applied')
    elif a.cmd=='import':
        from etl.importer import import_file
        for path in a.paths:print(json.dumps(import_file(path),default=str),flush=True)
    elif a.cmd=='fetch':
        from etl.archive import fetch_month
        for m in a.months:print(fetch_month(m))
    elif a.cmd=='train':
        from backend.ml import benchmark
        print(json.dumps(benchmark(a.origin,a.horizon),default=str))
    elif a.cmd=='project':
        from backend.projections import replay
        print(replay())
    elif a.cmd=='health':
        from backend.services import health
        print(json.dumps(health(),default=str))
    elif a.cmd=='demo-fixture':
        from etl.fixtures import documents
        from etl.importer import import_document
        for d in documents():print(import_document(d))
if __name__=='__main__':main()
