"""SQLite storage. Plain sqlite3 keeps the stack small; JSON columns hold flexible data."""
import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("ROUTEWISE_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "routewise.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',          -- draft | scored | approved
    criteria_json TEXT NOT NULL DEFAULT '[]',      -- list of criterion configs
    validation_json TEXT NOT NULL DEFAULT '{}'     -- last upload report
);
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL REFERENCES rounds(id),
    ext_id TEXT,
    address TEXT NOT NULL,
    neighborhood TEXT NOT NULL,
    lat REAL, lon REAL,
    data_json TEXT NOT NULL,                       -- numeric criterion values
    score REAL, prob REAL, amount REAL,
    breakdown_json TEXT,
    rank INTEGER
);
CREATE TABLE IF NOT EXISTS surveyors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
    round_id INTEGER NOT NULL,
    neighborhood TEXT NOT NULL,
    surveyor_id INTEGER,
    PRIMARY KEY (round_id, neighborhood)
);
CREATE TABLE IF NOT EXISTS routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    surveyor_id INTEGER NOT NULL,
    neighborhood TEXT NOT NULL,
    start_lat REAL, start_lon REAL,
    start_source TEXT,                             -- gps | centroid
    built_at TEXT
);
CREATE TABLE IF NOT EXISTS route_stops (
    route_id INTEGER NOT NULL,
    property_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    planned_seq INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',        -- pending | done | not_done
    reason TEXT,
    skips INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT,
    PRIMARY KEY (route_id, property_id)
);
CREATE TABLE IF NOT EXISTS visit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL,
    property_id INTEGER NOT NULL,
    action TEXT NOT NULL,                          -- done | not_done | skip
    reason TEXT,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS geocache (
    address TEXT PRIMARY KEY,
    lat REAL, lon REAL
);
"""

DEFAULT_SURVEYORS = ["דנה כהן", "יוסי לוי", "מיכל אברהם", "אבי מזרחי", "רונית פרץ"]


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str | None = None) -> None:
    with get_conn(path) as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM surveyors").fetchone()[0] == 0:
            conn.executemany("INSERT INTO surveyors(name) VALUES (?)", [(n,) for n in DEFAULT_SURVEYORS])


@contextmanager
def get_conn(path: str | None = None):
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def jloads(s, default=None):
    return json.loads(s) if s else default


def jdumps(o) -> str:
    return json.dumps(o, ensure_ascii=False)
