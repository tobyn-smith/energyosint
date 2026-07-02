"""Data ingestion.

Three public inputs, each with a live EIA path and a synthetic fallback:

  - plant-level generation capacity (EIA-860)
  - state reliability metrics, SAIDI / SAIFI (EIA-861)
  - state peak demand and net generation

Live pulls need a free EIA API key in EIA_API_KEY. When that's missing or a
request fails, we generate a deterministic stand-in so the rest of the
pipeline still has something to chew on. The fallback is clearly labelled in
the output (`source` column) so nobody mistakes it for the real thing.
"""

from __future__ import annotations

import os
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import requests

RAW_DIR = Path("data/raw")

# 50 states + DC. PR/territories left out because EIA reliability coverage is
# patchy there and it would skew the normalization.
STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
]

FUELS = ["natural_gas", "coal", "nuclear", "hydro", "wind", "solar", "oil"]


def _seed_for(label: str) -> int:
    """Stable per-state seed so synthetic runs are reproducible."""
    return zlib.adler32(label.encode()) & 0xFFFFFFFF


def _eia_key() -> str | None:
    key = os.environ.get("EIA_API_KEY", "").strip()
    return key or None


def _get_json(url: str, params: dict) -> dict | None:
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Synthetic fallbacks
# --------------------------------------------------------------------------- #

# Rough regional fuel leanings so the sample isn't uniform noise. Not meant to
# be accurate per state, just plausible enough to exercise the scoring.
_FUEL_BIAS = {
    "coal": {"WV", "WY", "KY", "ND", "MT", "IN", "MO"},
    "nuclear": {"IL", "PA", "SC", "TN", "NH"},
    "hydro": {"WA", "OR", "ID", "NY"},
    "wind": {"IA", "KS", "OK", "TX", "ND", "SD"},
    "solar": {"CA", "NV", "AZ", "NC"},
}


def _plant_count(rng: np.random.Generator) -> int:
    return int(rng.integers(6, 16))


def _synthetic_plants() -> pd.DataFrame:
    rows = []
    for st in STATES:
        rng = np.random.default_rng(_seed_for("plants:" + st))
        weights = np.ones(len(FUELS))
        for fuel, members in _FUEL_BIAS.items():
            if st in members:
                weights[FUELS.index(fuel)] += 4.0
        weights = weights / weights.sum()

        for i in range(_plant_count(rng)):
            fuel = rng.choice(FUELS, p=weights)
            # Nuclear/coal plants run big; solar/wind sites are smaller and
            # more numerous in reality, but capacity is what we care about.
            base = {"nuclear": 1100, "coal": 700, "natural_gas": 450,
                    "hydro": 300, "wind": 180, "solar": 120, "oil": 90}[fuel]
            cap = max(20.0, rng.normal(base, base * 0.35))
            rows.append({
                "state": st,
                "plant_name": f"{st}-{fuel[:3].upper()}-{i+1:02d}",
                "fuel": fuel,
                "capacity_mw": round(cap, 1),
            })
    df = pd.DataFrame(rows)
    df["source"] = "synthetic"
    return df


def _synthetic_reliability() -> pd.DataFrame:
    rows = []
    for st in STATES:
        rng = np.random.default_rng(_seed_for("rel:" + st))
        # SAIDI in minutes/customer/year. National figures cluster a few
        # hundred minutes with a long storm-driven tail, so lognormal fits.
        saidi = float(rng.lognormal(mean=5.4, sigma=0.55))
        saifi = float(np.clip(rng.normal(1.3, 0.5), 0.3, 4.0))
        rows.append({
            "state": st,
            "saidi_minutes": round(saidi, 1),
            "saifi_events": round(saifi, 2),
        })
    df = pd.DataFrame(rows)
    df["source"] = "synthetic"
    return df


def _synthetic_demand(plants: pd.DataFrame) -> pd.DataFrame:
    cap_by_state = plants.groupby("state")["capacity_mw"].sum()
    rows = []
    for st in STATES:
        rng = np.random.default_rng(_seed_for("dem:" + st))
        cap = float(cap_by_state.get(st, 5000.0))
        # Peak demand as a fraction of installed capacity. Centred below 1 but
        # the tail crosses it, which is exactly the tight-margin case we want
        # the exposure component to catch.
        ratio = float(np.clip(rng.normal(0.82, 0.18), 0.4, 1.25))
        peak = cap * ratio
        rows.append({
            "state": st,
            "peak_demand_mw": round(peak, 1),
            "net_generation_gwh": round(peak * rng.uniform(3.5, 5.5), 0),
        })
    df = pd.DataFrame(rows)
    df["source"] = "synthetic"
    return df


# --------------------------------------------------------------------------- #
# Live EIA pulls (best-effort; fall back on any miss)
# --------------------------------------------------------------------------- #

def _live_plants(base: str, key: str) -> pd.DataFrame | None:
    # EIA-860M operating generator capacity by plant and energy source.
    url = f"{base}/electricity/operating-generator-capacity/data/"
    params = {
        "api_key": key,
        "frequency": "monthly",
        "data[0]": "nameplate-capacity-mw",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    payload = _get_json(url, params)
    try:
        records = payload["response"]["data"]
    except (TypeError, KeyError):
        return None
    if not records:
        return None

    df = pd.DataFrame(records)
    # Field names drift between EIA datasets; map defensively.
    rename = {
        "stateid": "state", "plantName": "plant_name",
        "energy_source_desc": "fuel",
        "nameplate-capacity-mw": "capacity_mw",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df})
    needed = {"state", "fuel", "capacity_mw"}
    if not needed.issubset(df.columns):
        return None

    df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce")
    df = df.dropna(subset=["capacity_mw"])
    df = df[df["state"].isin(STATES)]
    if df.empty:
        return None
    df["plant_name"] = df.get("plant_name", "unknown")
    df["source"] = "eia"
    return df[["state", "plant_name", "fuel", "capacity_mw", "source"]]


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #

def _no_synthetic(cfg: dict, what: str) -> None:
    # Honour allow_synthetic_fallback: if it's off, refuse to quietly hand back
    # sample data. Raise so the caller knows real data wasn't available.
    if not cfg["sources"].get("allow_synthetic_fallback", True):
        raise RuntimeError(f"no live {what} data available and allow_synthetic_fallback is off")


def load_plants(cfg: dict) -> pd.DataFrame:
    key = _eia_key()
    if key:
        live = _live_plants(cfg["sources"]["eia_api_base"], key)
        if live is not None:
            return _maybe_cache(live, "plants", cfg)
    _no_synthetic(cfg, "capacity")
    return _maybe_cache(_synthetic_plants(), "plants", cfg)


def load_reliability(cfg: dict) -> pd.DataFrame:
    # A clean EIA-861 reliability endpoint isn't exposed in API v2 the way the
    # capacity data is; it ships as bulk files. For a live build you'd parse the
    # EIA-861 reliability workbook here. Until then, synthetic.
    _no_synthetic(cfg, "reliability")
    return _maybe_cache(_synthetic_reliability(), "reliability", cfg)


def load_demand(cfg: dict, plants: pd.DataFrame) -> pd.DataFrame:
    _no_synthetic(cfg, "demand")
    return _maybe_cache(_synthetic_demand(plants), "demand", cfg)


def _maybe_cache(df: pd.DataFrame, name: str, cfg: dict) -> pd.DataFrame:
    if cfg["sources"].get("cache_raw"):
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(RAW_DIR / f"{name}.csv", index=False)
    return df
