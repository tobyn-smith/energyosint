"""A small JSON API over the scored data.

It reads whatever the pipeline last wrote to the SQLite store and serves it, and
it can re-rank the states live for any set of weights by calling the same scoring
code the pipeline uses, so the two never drift apart. Run the pipeline first so
there is a run to serve.

    pip install -r requirements-api.txt
    uvicorn server:app --reload
    # then open http://127.0.0.1:8000/docs

Endpoints:
    GET /health
    GET /api/runs
    GET /api/states                     the latest scored table
    GET /api/states/{code}              one state
    GET /api/score?wO=&wC=&wD=&top=     re-rank live for custom weights
    GET /api/regions?level=region|division
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from grid import scoring, store
from grid.regions import STATE_NAMES, lookup

CONFIG = "config.yaml"
COMPONENTS = ["outage_burden", "infra_concentration", "exposure_deficit"]

app = FastAPI(title="Grid Resilience Exposure Index API", version="1.0")

# Allow the static site (or anything else) to call this if it is ever deployed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
)


def _config() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _db_path() -> str:
    return _config().get("database", {}).get("path", "outputs/index.db")


def _conn():
    """A fresh connection per request; sqlite connections are not thread safe."""
    path = Path(_db_path())
    if not path.exists():
        raise HTTPException(503, "no database yet, run `python pipeline.py` first")
    return store.connect(path)


def _latest(conn) -> int:
    run_id = store.latest_run_id(conn)
    if run_id is None:
        raise HTTPException(503, "no runs stored yet, run `python pipeline.py` first")
    return run_id


def _named(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.insert(1, "name", df["state"].map(STATE_NAMES))
    return df


@app.get("/health")
def health() -> dict:
    path = Path(_db_path())
    if not path.exists():
        return {"status": "empty", "runs": 0}
    conn = store.connect(path)
    try:
        return {"status": "ok", "runs": int(len(store.list_runs(conn)))}
    finally:
        conn.close()


@app.get("/api/runs")
def runs() -> list[dict]:
    conn = _conn()
    try:
        return store.list_runs(conn).to_dict("records")
    finally:
        conn.close()


@app.get("/api/states")
def states() -> list[dict]:
    conn = _conn()
    try:
        df = store.load_scores(conn, _latest(conn))
        return _named(df).to_dict("records")
    finally:
        conn.close()


@app.get("/api/states/{code}")
def state(code: str) -> dict:
    conn = _conn()
    try:
        df = store.load_scores(conn, _latest(conn))
        row = df[df["state"] == code.upper()]
        if row.empty:
            raise HTTPException(404, f"no state {code!r} in the latest run")
        return _named(row).iloc[0].to_dict()
    finally:
        conn.close()


@app.get("/api/score")
def score(
    wO: float = Query(None, description="outage burden weight"),
    wC: float = Query(None, description="concentration weight"),
    wD: float = Query(None, description="exposure deficit weight"),
    top: int = Query(0, ge=0, description="limit to the top N, 0 for all"),
) -> list[dict]:
    """Re-rank the latest run's states for custom weights, using the same scoring
    code the pipeline runs. Missing weights fall back to the config defaults."""
    cfg = _config()
    defaults = cfg["weights"]
    weights = {
        "outage_burden": defaults["outage_burden"] if wO is None else wO,
        "infra_concentration": defaults["infra_concentration"] if wC is None else wC,
        "exposure_deficit": defaults["exposure_deficit"] if wD is None else wD,
    }
    if any(v < 0 for v in weights.values()):
        raise HTTPException(400, "weights cannot be negative")
    if sum(weights.values()) <= 0:
        raise HTTPException(400, "at least one weight must be above zero")

    conn = _conn()
    try:
        inputs = store.load_inputs(conn, _latest(conn))
    finally:
        conn.close()

    scored = scoring.score(inputs, weights=weights, normalize=cfg["scoring"]["normalize"])
    out = _named(scored)[["rank", "state", "name", "exposure_score", "driver"]]
    if top:
        out = out.head(top)
    return out.to_dict("records")


@app.get("/api/regions")
def regions(level: str = Query("region", pattern="^(region|division)$")) -> list[dict]:
    conn = _conn()
    try:
        df = store.load_scores(conn, _latest(conn))
    finally:
        conn.close()

    df = df.copy()
    df["group"] = df["state"].map(lookup(level))
    cols = ["exposure_score"] + COMPONENTS
    summary = (
        df.dropna(subset=["group"])
        .groupby("group")[cols]
        .mean()
        .round(2)
        .sort_values("exposure_score", ascending=False)
    )
    summary["top_driver"] = summary[COMPONENTS].idxmax(axis=1)
    return summary.reset_index().rename(columns={"group": level}).to_dict("records")
