"""A small SQLite store for pipeline runs.

Each run keeps two things: the scored table (what gets served straight out) and
the raw state inputs (so the API can re-score under different weights without
re-reading any files). Everything goes through stdlib sqlite3 plus pandas, so
there is no extra dependency.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DEFAULT_DB = Path("outputs/index.db")

# The raw inputs scoring needs, so a run can be re-scored from the DB alone.
INPUT_COLS = [
    "state", "total_capacity_mw", "n_plants", "fuel_hhi", "top_plant_share",
    "n_fuels", "saidi_minutes", "saifi_events", "peak_demand_mw", "capacity_margin",
]


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    # Only the runs table has a fixed shape. The scores/inputs tables are created
    # by pandas on first write, so they follow whatever columns the frame has and
    # never drift out of step with the pipeline.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source     TEXT NOT NULL,
            normalize  TEXT NOT NULL,
            n_states   INTEGER NOT NULL
        )
        """
    )
    conn.commit()


def save_run(conn: sqlite3.Connection, scored: pd.DataFrame, state_table: pd.DataFrame,
             *, source: str, normalize: str, created_at: str) -> int:
    """Write one run and return its id. `created_at` is passed in (ISO string)
    so the caller controls the clock and the write stays reproducible in tests."""
    cur = conn.execute(
        "INSERT INTO runs (created_at, source, normalize, n_states) VALUES (?, ?, ?, ?)",
        (created_at, source, normalize, int(len(scored))),
    )
    run_id = int(cur.lastrowid)

    scored = scored.copy()
    scored.insert(0, "run_id", run_id)
    _append(conn, "scores", scored)

    keep = [c for c in INPUT_COLS if c in state_table.columns]
    inputs = state_table[keep].copy()
    inputs.insert(0, "run_id", run_id)
    _append(conn, "inputs", inputs)

    conn.commit()
    return run_id


def _append(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    """Append a frame, coping with the columns having changed since the last run.

    Plain to_sql(append) raises if the frame and the table disagree on columns, so
    a change to what the pipeline keeps would break every later run against an
    existing database. Widen the table for new columns and leave old ones null.
    """
    existing = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if not existing:                      # first write creates the table
        df.to_sql(table, conn, if_exists="append", index=False)
        return

    for col in df.columns:
        if col not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN "{col}"')
            existing.append(col)

    for col in existing:
        if col not in df.columns:
            df[col] = None

    df[existing].to_sql(table, conn, if_exists="append", index=False)


def latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return int(row[0]) if row else None


def list_runs(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM runs ORDER BY id DESC", conn)


def load_scores(conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT * FROM scores WHERE run_id = ? ORDER BY rank", conn, params=(run_id,)
    )
    return df.drop(columns=["run_id"], errors="ignore")


def load_inputs(conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT * FROM inputs WHERE run_id = ?", conn, params=(run_id,)
    )
    return df.drop(columns=["run_id"], errors="ignore")
