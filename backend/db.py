from contextlib import contextmanager
from pathlib import Path
import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

@contextmanager
def connect():
    with psycopg.connect(os.getenv('DATABASE_URL', 'postgresql://kerykeion:local-demo-only@localhost:55433/kerykeion'), row_factory=dict_row) as conn:
        yield conn

def migrate():
    with connect() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migration(name text PRIMARY KEY, applied_at timestamptz DEFAULT now())')
        for file in sorted((ROOT / 'migrations').glob('*.sql')):
            if not conn.execute('SELECT 1 FROM schema_migration WHERE name=%s', (file.name,)).fetchone():
                conn.execute(file.read_text())
                conn.execute('INSERT INTO schema_migration(name) VALUES (%s)', (file.name,))
