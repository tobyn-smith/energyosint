"""Turn the three raw tables into one state-level frame for scoring.

Most of the work is here: collapsing plant rows into the concentration
measures, then joining reliability and demand onto the same key.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _fuel_hhi(group: pd.DataFrame) -> float:
    """Herfindahl index of capacity across fuels (0-10000).

    A state running everything off one fuel scores near 10000; a balanced
    mix sits low. This is our stand-in for "how much does the grid lean on a
    single resource type".
    """
    shares = group.groupby("fuel")["capacity_mw"].sum()
    frac = shares / shares.sum()
    return float((frac**2).sum() * 10_000)


def _top_plant_share(group: pd.DataFrame) -> float:
    total = group["capacity_mw"].sum()
    return float(group["capacity_mw"].max() / total) if total else np.nan


def concentration_by_state(plants: pd.DataFrame) -> pd.DataFrame:
    out = []
    for state, grp in plants.groupby("state"):
        out.append({
            "state": state,
            "total_capacity_mw": round(grp["capacity_mw"].sum(), 1),
            "n_plants": len(grp),
            "fuel_hhi": round(_fuel_hhi(grp), 1),
            "top_plant_share": round(_top_plant_share(grp), 4),
            "n_fuels": grp["fuel"].nunique(),
        })
    return pd.DataFrame(out)


def build_state_table(plants, reliability, demand) -> pd.DataFrame:
    df = concentration_by_state(plants)
    df = df.merge(reliability.drop(columns=["source"], errors="ignore"), on="state", how="left")
    df = df.merge(demand.drop(columns=["source"], errors="ignore"), on="state", how="left")

    # Capacity margin: installed capacity relative to peak demand. Below ~1.1
    # is a tight grid. Guard against a zero/NaN peak before dividing.
    peak = df["peak_demand_mw"].replace(0, np.nan)
    df["capacity_margin"] = (df["total_capacity_mw"] / peak).round(3)

    # Flag anything still missing after the joins rather than silently scoring
    # a half-empty row.
    key_cols = ["fuel_hhi", "saidi_minutes", "capacity_margin"]
    incomplete = df[key_cols].isna().any(axis=1)
    if incomplete.any():
        missing = ", ".join(df.loc[incomplete, "state"])
        print(f"  [clean] dropping states with gaps after join: {missing}")
        df = df[~incomplete].reset_index(drop=True)

    return df.sort_values("state").reset_index(drop=True)
