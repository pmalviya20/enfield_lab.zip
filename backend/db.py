"""
Database access layer for Enfield Lab.

Local development uses SQLite (zero setup, ships with Python).
Production (Render) uses PostgreSQL (Neon) via the DATABASE_URL env var.

The rest of the app writes plain SQL with "?" placeholders (SQLite style).
This module transparently rewrites them to "%s" for PostgreSQL, so route
code never needs to know which engine is active.
"""
import os
import re
import sqlite3
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(os.path.dirname(BASE_DIR), "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
SQLITE_PATH = os.path.join(INSTANCE_DIR, "enfield.db")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
ENGINE = "postgres" if DATABASE_URL.startswith(("postgres://", "postgresql://")) else "sqlite"

_local = threading.local()
_pg_pool = None


def _get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        import psycopg2
        from psycopg2 import pool as pg_pool

        url = DATABASE_URL
        # Render/Neon sometimes give postgres:// which psycopg2 also accepts,
        # but normalize just in case a driver-specific prefix is required.
        _pg_pool = pg_pool.ThreadedConnectionPool(1, 10, dsn=url, sslmode="require")
    return _pg_pool


def _qmark_to_pyformat(sql: str) -> str:
    # Convert SQLite-style "?" placeholders to psycopg2-style "%s".
    # Safe because application SQL never contains a literal "?" character.
    return sql.replace("?", "%s")


class Row(dict):
    """Dict-like row that also supports attribute access, e.g. row.id"""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e


def get_conn():
    if ENGINE == "sqlite":
        conn = getattr(_local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(SQLITE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            _local.conn = conn
        return conn
    else:
        pool = _get_pg_pool()
        conn = getattr(_local, "pg_conn", None)
        if conn is None or conn.closed:
            conn = pool.getconn()
            _local.pg_conn = conn
        return conn


def _rows_to_dicts(cursor, rows):
    if ENGINE == "sqlite":
        return [Row(dict(r)) for r in rows]
    cols = [d[0] for d in cursor.description] if cursor.description else []
    return [Row(dict(zip(cols, r))) for r in rows]


def query(sql, params=()):
    """Run a SELECT and return a list of Row dicts."""
    conn = get_conn()
    sql2 = sql if ENGINE == "sqlite" else _qmark_to_pyformat(sql)
    cur = conn.cursor()
    try:
        cur.execute(sql2, params)
        rows = cur.fetchall()
        result = _rows_to_dicts(cur, rows)
    except Exception:
        # Without this, a single failed statement leaves a Postgres
        # connection "aborted" - every later query on this same persistent
        # per-thread connection would then fail too, until the process
        # restarts. Roll back immediately so the connection stays usable.
        conn.rollback()
        raise
    finally:
        cur.close()
    return result


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    """Run an INSERT/UPDATE/DELETE and commit. Returns rowcount."""
    conn = get_conn()
    sql2 = sql if ENGINE == "sqlite" else _qmark_to_pyformat(sql)
    cur = conn.cursor()
    try:
        cur.execute(sql2, params)
        conn.commit()
        rc = cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    return rc


def insert_and_get_id(sql, params=()):
    """Run an INSERT and return the new row's id, across SQLite/Postgres."""
    conn = get_conn()
    if ENGINE == "sqlite":
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            conn.commit()
            new_id = cur.lastrowid
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
        return new_id
    else:
        sql2 = _qmark_to_pyformat(sql)
        if "RETURNING" not in sql2.upper():
            sql2 = sql2.rstrip().rstrip(";") + " RETURNING id"
        cur = conn.cursor()
        try:
            cur.execute(sql2, params)
            new_id = cur.fetchone()[0]
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
        return new_id


def executemany(sql, seq_of_params):
    conn = get_conn()
    sql2 = sql if ENGINE == "sqlite" else _qmark_to_pyformat(sql)
    cur = conn.cursor()
    try:
        cur.executemany(sql2, seq_of_params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def init_db():
    """Create tables if they don't already exist."""
    schema_file = "schema_pg.sql" if ENGINE == "postgres" else "schema.sql"
    path = os.path.join(BASE_DIR, schema_file)
    with open(path, "r") as f:
        script = f.read()

    conn = get_conn()
    if ENGINE == "sqlite":
        conn.executescript(script)
        conn.commit()
    else:
        cur = conn.cursor()
        # Strip full-line "--" comments before splitting on ";" - a semicolon
        # anywhere in a comment's prose (e.g. "an admin must approve it; and
        # ...") would otherwise be mistaken for a statement boundary and
        # corrupt the next CREATE TABLE. This is a naive splitter, not a real
        # SQL parser, so schema comments must stay on their own "--" lines.
        cleaned_lines = [line for line in script.splitlines() if not line.strip().startswith("--")]
        cleaned_script = "\n".join(cleaned_lines)
        statements = [s.strip() for s in cleaned_script.split(";") if s.strip()]
        for stmt in statements:
            try:
                cur.execute(stmt)
            except Exception as e:
                # Multiple gunicorn workers can race to create tables on the
                # very first deploy; "already exists" from a concurrent
                # CREATE TABLE/INDEX IF NOT EXISTS is harmless - roll back
                # just this statement and continue. Logged (not silenced) so
                # a genuine schema bug shows up in the Render logs instead of
                # silently leaving a table missing.
                conn.rollback()
                print(f"[init_db] skipping statement due to: {e}\n  statement: {stmt[:200]}")
        conn.commit()
        cur.close()

    _ensure_seed_rows()


def _ensure_seed_rows():
    row = query_one("SELECT id FROM business_profile LIMIT 1")
    if not row:
        execute(
            "INSERT INTO business_profile (business_name, tagline, address, phone) VALUES (?, ?, ?, ?)",
            (
                "Enfield Lab",
                "By The Rider - For The Rider - From The Rider",
                "Shop No. 1, Chandan Pride, Opp. Police Station, Near Pantnagar, Ghatkopar East, Mumbai, Maharashtra 400077",
                "08451093010",
            ),
        )
    supplier = query_one("SELECT id FROM suppliers WHERE name = ?", ("Royal Enfield (RAM Motorcycles)",))
    if not supplier:
        execute(
            "INSERT INTO suppliers (name) VALUES (?)",
            ("Royal Enfield (RAM Motorcycles)",),
        )
