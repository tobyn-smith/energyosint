"""Turn the three raw tables into one state-level frame for scoring.

Most of the work is here: collapsing plant rows into the concentration
measures, then joining reliability and demand onto the same key.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def concentration_by_state(plants: pd.DataFrame) -> pd.DataFrame:
    """One row per state with total capacity and the concentration measures."""
    def compute_state_metrics(state_group):
        total_cap = state_group["capacity_mw"].sum()

        # Herfindahl index of capacity across fuels (0-10000). High means the
        # state leans on one fuel; low means a spread.
        fuel_shares = state_group.groupby("fuel")["capacity_mw"].sum()
        fuel_frac = fuel_shares / total_cap
        fuel_hhi = float((fuel_frac**2).sum() * 10_000)

        # Work at plant level: real EIA data has several generator rows per
        # plant, so roll them up before counting plants or taking the largest.
        # On the synthetic sample there is one row per plant, so this is a no-op.
        plant_caps = state_group.groupby("plant_name")["capacity_mw"].sum()
        top_share = float(plant_caps.max() / total_cap) if total_cap else np.nan

        return pd.Series({
            "total_capacity_mw": round(total_cap, 1),
            "n_plants": int(plant_caps.size),
            "fuel_hhi": round(fuel_hhi, 1),
            "top_plant_share": round(top_share, 4),
            "n_fuels": state_group["fuel"].nunique(),
        })

    result = plants.groupby("state", as_index=False).apply(compute_state_metrics).reset_index(drop=True)
    return result[["state", "total_capacity_mw", "n_plants", "fuel_hhi", "top_plant_share", "n_fuels"]]


def build_state_table(plants, reliability, demand) -> pd.DataFrame:
    df = concentration_by_state(plants)
    df = df.merge(reliability.drop(columns=["source"], errors="ignore"), on="state", how="left")
    df = df.merge(demand.drop(columns=["source"], errors="ignore"), on="state", how="left")

    # Capacity margin: installed capacity relative to peak demand. Below ~1.1
    # is a tight grid. Guard against a zero/NaN peak before dividing.
    peak = df["peak_demand_mw"].replace(0, np.nan)
    df["capacity_margin"] = (df["total_capacity_mw"] / peak).round(3)

    # Drop any state missing an input the score depends on, rather than letting
    # a NaN slip through and blow up the ranking later. These are all the
    # columns scoring.py reads.
    key_cols = ["fuel_hhi", "top_plant_share", "n_fuels",
                "saidi_minutes", "saifi_events", "capacity_margin"]
    incomplete = df[key_cols].isna().any(axis=1)
    if incomplete.any():
        missing = ", ".join(df.loc[incomplete, "state"])
        print(f"  [clean] dropping states with gaps after join: {missing}")
        df = df[~incomplete].reset_index(drop=True)

    return df.sort_values("state").reset_index(drop=True)
