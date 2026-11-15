"""SQLite storage. Standard library only; game objects are stored as JSON text.

No migrations: if the schema changes during the hackathon, delete the file.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS missions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scenario_id TEXT NOT NULL,
    name        TEXT NOT NULL,
    design_json TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    user_id         TEXT REFERENCES users(id) ON DELETE CASCADE,      -- NULL = guest run
    mission_id      TEXT REFERENCES missions(id) ON DELETE SET NULL,
    scenario_id     TEXT NOT NULL,
    catalog_version TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    status          TEXT NOT NULL,
    state_json      TEXT NOT NULL,   -- full RunState, includes the design snapshot
    debrief_json    TEXT,
    outcome         TEXT,
    score_total     REAL,
    created_at      TEXT NOT NULL,
    completed_at    TEXT
);
CREATE TABLE IF NOT EXISTS simulation_runs (   -- real-data engine (engine_v4); always complete
    id                       TEXT PRIMARY KEY,
    user_id                  TEXT REFERENCES users(id) ON DELETE CASCADE,   -- NULL = guest run
    name                     TEXT,
    scenario_id              TEXT NOT NULL,
    dataset_id               TEXT,
    engine_version           TEXT NOT NULL,
    seed                     INTEGER NOT NULL,
    feasibility              TEXT NOT NULL,   -- FEASIBLE or CONDITIONAL (INFEASIBLE cannot launch)
    outcome                  TEXT NOT NULL,
    score_total              REAL,
    uses_parameter_overrides INTEGER NOT NULL DEFAULT 0,
    configuration_json       TEXT NOT NULL,
    scenario_parameters_json TEXT NOT NULL,
    result_json              TEXT NOT NULL,   -- the full engine result
    created_at               TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_simulation_runs_user ON simulation_runs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_missions_user ON missions(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_mission ON runs(mission_id, created_at);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """One shared connection guarded by a lock (FastAPI runs handlers in threads)."""

    def __init__(self, path: str = ":memory:") -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Run a write statement; returns the number of rows changed."""
        with self._lock:
            try:
                cursor = self._conn.execute(sql, params)
                self._conn.commit()
                return cursor.rowcount
            except Exception:
                self._conn.rollback()
                raise

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
