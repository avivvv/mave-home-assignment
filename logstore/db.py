import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hpc.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (
    id        INTEGER PRIMARY KEY,
    component TEXT NOT NULL,
    state     TEXT NOT NULL,
    template  TEXT NOT NULL,
    UNIQUE (component, state, template)
);
CREATE TABLE IF NOT EXISTS logs (
    id           INTEGER PRIMARY KEY,
    event_id     INTEGER NOT NULL,
    node         TEXT NOT NULL,
    component    TEXT NOT NULL,
    state        TEXT NOT NULL,
    time         REAL NOT NULL,
    flag         INTEGER NOT NULL,
    message      TEXT NOT NULL,
    bad_time     INTEGER NOT NULL,
    ts           TEXT,
    original_log TEXT NOT NULL,
    template_id  INTEGER NOT NULL REFERENCES templates(id),
    n_copies     INTEGER NOT NULL DEFAULT 1,
    UNIQUE (node, component, state, time, message)
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS ix_logs_ts ON logs(ts);
CREATE INDEX IF NOT EXISTS ix_logs_template_ts ON logs(template_id, ts);
"""


def connect(path=DEFAULT_DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)


def create_indexes(conn):
    conn.executescript(INDEXES)
