"""Roll the state scores up to US Census regions.

The index is per state, but it is often more useful to ask which part of the
country looks most exposed. This groups the states into the four Census regions,
then reports the average score and the average of each component, so you can see
both where exposure is highest and what is driving it.

Run the main pipeline first so outputs/exposure_index.csv exists.

    python analysis/regional_summary.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

INDEX = Path("outputs/exposure_index.csv")

# US Census Bureau regions. DC sits in the South Atlantic division, as the
# Census groups it.
CENSUS_REGION = {
    "Northeast": ["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"],
    "Midwest":   ["IL", "IN", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"],
    "South":     ["DE", "DC", "FL", "GA", "MD", "NC", "SC", "VA", "WV",
                  "AL", "KY", "MS", "TN", "AR", "LA", "OK", "TX"],
    "West":      ["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"],
}

COMPONENTS = ["outage_burden", "infra_concentration", "exposure_deficit"]


def _lookup():
    return {st: region for region, states in CENSUS_REGION.items() for st in states}


def main():
    if not INDEX.exists():
        raise SystemExit("run `python pipeline.py` first, outputs/exposure_index.csv is missing")

    df = pd.read_csv(INDEX)
    df["region"] = df["state"].map(_lookup())

    missed = df.loc[df["region"].isna(), "state"].tolist()
    if missed:
        print("not mapped to a region:", ", ".join(missed))

    cols = ["exposure_score"] + COMPONENTS
    summary = (
        df.dropna(subset=["region"])
        .groupby("region")[cols]
        .mean()
        .sort_values("exposure_score", ascending=False)
        .round(2)
    )
    # Which component stands highest on average tells you what drives the region.
    summary["top_driver"] = summary[COMPONENTS].idxmax(axis=1)

    print(summary.to_string())
    summary.to_csv("outputs/regional_summary.csv")

    order = summary.index[::-1]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.barh(order, summary.loc[order, "exposure_score"], color="#c14625")
    ax.set_xlabel("Average exposure score")
    ax.set_title("Average exposure by US Census region")
    for i, v in enumerate(summary.loc[order, "exposure_score"]):
        ax.text(v + 0.6, i, f"{v:.0f}", va="center", fontsize=8)
    ax.margins(x=0.12)
    fig.tight_layout()
    fig.savefig("outputs/regional_exposure.png", dpi=130)
    plt.close(fig)

    print("\nwrote outputs/regional_summary.csv and outputs/regional_exposure.png")


if __name__ == "__main__":
    main()
