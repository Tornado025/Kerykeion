"""Back up PostgreSQL and verify restoration in a new disposable database."""
import json,subprocess,uuid
from backend.db import ROOT,connect


def docker(*args,**kwargs):
    return subprocess.run(['docker','compose','exec','-T','postgres',*args],check=True,**kwargs)


def main():
    backup=ROOT/'artifacts/kerykeion.dump';temporary='kerykeion_check_'+uuid.uuid4().hex[:12]
    # Export one consistent snapshot for both counts and pg_dump while workers run.
    with connect() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        snapshot=c.execute('SELECT pg_export_snapshot() s').fetchone()['s']
        tables=[r['tablename'] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        counts={t:c.execute(f'SELECT count(*) n FROM "{t}"').fetchone()['n'] for t in tables}
        fingerprint_sql=lambda t: f"SELECT sum(('x'||substr(md5(row_to_json(t)::text),1,16))::bit(64)::bigint)::text FROM \"{t}\" t"
        fingerprints={t:c.execute(fingerprint_sql(t)).fetchone()['sum'] for t in tables if t not in ('drift_prediction','feature_materialization')}
        with backup.open('wb') as f:docker('pg_dump','-U','kerykeion','-Fc','--snapshot='+snapshot,'kerykeion',stdout=f)
    docker('createdb','-U','kerykeion',temporary)
    try:
        with backup.open('rb') as f:docker('pg_restore','-U','kerykeion','--exit-on-error','-d',temporary,stdin=f)
        restored={}
        for table in tables:
            value=docker('psql','-U','kerykeion','-d',temporary,'-At','-c',f'SELECT count(*) FROM "{table}"',capture_output=True,text=True)
            restored[table]=int(value.stdout.strip())
        assert restored==counts,(counts,restored)
        restored_fingerprints={}
        for table in fingerprints:
            value=docker('psql','-U','kerykeion','-d',temporary,'-At','-c',fingerprint_sql(table),capture_output=True,text=True)
            restored_fingerprints[table]=value.stdout.strip() or None
        assert restored_fingerprints==fingerprints

        report=dict(passed=True,backup=str(backup),backup_bytes=backup.stat().st_size,table_counts=counts,restore_counts=restored,domain_fingerprints=fingerprints)
        (ROOT/'artifacts/backup-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:
        # Only the uniquely named disposable database created by this invocation.
        docker('dropdb','-U','kerykeion',temporary)

if __name__=='__main__':main()
