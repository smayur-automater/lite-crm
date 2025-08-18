
"""
Migrate SQLite lite_crm.db to Postgres (DATABASE_URL).
Usage:
    pip install psycopg2-binary
    python migrate_to_postgres.py
Environment:
    DATABASE_URL=postgres://USER:PASSWORD@HOST:PORT/DBNAME
"""
import os, sqlite3, psycopg2, psycopg2.extras

DB_PATH = "lite_crm.db"
PG_URL = os.getenv("DATABASE_URL")

assert PG_URL, "Set DATABASE_URL env var for Postgres."

def fetch_sqlite(table):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [c[1] for c in cur.fetchall()]
    rows = con.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    con.close()
    return cols, rows

def copy_table(pg, table):
    cols, rows = fetch_sqlite(table)
    cols_pg = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    with pg.cursor() as c:
        # create table if not exists (simple schema; adjust as needed)
        # NOTE: For production, use migrations/DDL. Here we assume target tables already created by app.
        if rows:
            c.executemany(f"INSERT INTO {table} ({cols_pg}) VALUES ({placeholders}) ON CONFLICT DO NOTHING", rows)

with psycopg2.connect(PG_URL) as pg:
    for t in ["users","workspaces","memberships","invites","password_resets","companies","contacts","deals","tasks","notes"]:
        copy_table(pg, t)
    pg.commit()
    print("Migration complete.")
