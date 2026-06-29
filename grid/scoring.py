"""Composite scoring.

Each of the three components is built from the cleaned columns, normalized
onto a common scale, then combined with the configured weights. Higher
composite = more exposed / less resilient.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd else s * 0.0


def _minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    return (s - lo) / (hi - lo) if hi > lo else s * 0.0


def _normalize(s: pd.Series, how: str) -> pd.Series:
    return _minmax(s) if how == "minmax" else _zscore(s)


def _components(df: pd.DataFrame) -> pd.DataFrame:
    """Raw (pre-normalization) component values, all oriented so higher=worse."""
    out = pd.DataFrame({"state": df["state"]})

    # Outage burden: SAIDI carries most of it, SAIFI as a lighter signal.
    # Both already point the right way (more minutes / more events = worse).
    saidi = _zscore(df["saidi_minutes"])
    saifi = _zscore(df["saifi_events"])
    out["outage_burden"] = 0.7 * saidi + 0.3 * saifi

    # Infrastructure concentration: fuel HHI plus how much rides on the single
    # largest plant. Both higher = more single-point exposure.
    out["infra_concentration"] = (
        0.6 * _zscore(df["fuel_hhi"]) + 0.4 * _zscore(df["top_plant_share"])
    )

    # Exposure deficit: tight capacity margins and thin fuel diversity. A
    # smaller margin is worse, so flip its sign; same for the fuel count.
    margin_gap = -_zscore(df["capacity_margin"])
    diversity_gap = -_zscore(df["n_fuels"].astype(float))
    out["exposure_deficit"] = 0.65 * margin_gap + 0.35 * diversity_gap

    return out


def score(df: pd.DataFrame, weights: dict, normalize: str = "zscore") -> pd.DataFrame:
    comp = _components(df)
    cols = ["outage_burden", "infra_concentration", "exposure_deficit"]

    # Re-normalize each blended component so the weights act on a level field.
    for c in cols:
        comp[c] = _normalize(comp[c], normalize)

    w = np.array([weights[c] for c in cols], dtype=float)
    w = w / w.sum()
    comp["exposure_index"] = comp[cols].to_numpy() @ w

    # A 0-100 version reads better in a table than raw z-scores.
    comp["exposure_score"] = (_minmax(comp["exposure_index"]) * 100).round(1)

    result = df.merge(comp, on="state")
    result["rank"] = result["exposure_score"].rank(ascending=False, method="min").astype(int)
    return result.sort_values("rank").reset_index(drop=True)
