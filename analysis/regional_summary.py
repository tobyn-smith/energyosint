"""Roll the state scores up to US Census regions, or the finer divisions.

The index is per state, but it is often more useful to ask which part of the
country looks most exposed. This groups the states and reports the average score
and the average of each component, so you can see both where exposure is highest
and what is driving it.

Run the main pipeline first so outputs/exposure_index.csv exists.

    python analysis/regional_summary.py                # four census regions
    python analysis/regional_summary.py --level division   # nine divisions
"""

import argparse
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

# The nine Census divisions, which split the four regions further.
CENSUS_DIVISION = {
    "New England":        ["CT", "ME", "MA", "NH", "RI", "VT"],
    "Middle Atlantic":    ["NJ", "NY", "PA"],
    "East North Central": ["IL", "IN", "MI", "OH", "WI"],
    "West North Central": ["IA", "KS", "MN", "MO", "NE", "ND", "SD"],
    "South Atlantic":     ["DE", "DC", "FL", "GA", "MD", "NC", "SC", "VA", "WV"],
    "East South Central": ["AL", "KY", "MS", "TN"],
    "West South Central": ["AR", "LA", "OK", "TX"],
    "Mountain":           ["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY"],
    "Pacific":            ["AK", "CA", "HI", "OR", "WA"],
}

GROUPINGS = {"region": CENSUS_REGION, "division": CENSUS_DIVISION}
COMPONENTS = ["outage_burden", "infra_concentration", "exposure_deficit"]


def _lookup(grouping):
    return {st: name for name, states in grouping.items() for st in states}


def main():
    ap = argparse.ArgumentParser(description="roll the scores up to census regions or divisions")
    ap.add_argument("--level", choices=["region", "division"], default="region")
    args = ap.parse_args()

    if not INDEX.exists():
        raise SystemExit("run `python pipeline.py` first, outputs/exposure_index.csv is missing")

    level = args.level
    df = pd.read_csv(INDEX)
    df[level] = df["state"].map(_lookup(GROUPINGS[level]))

    missed = df.loc[df[level].isna(), "state"].tolist()
    if missed:
        print(f"not mapped to a {level}:", ", ".join(missed))

    cols = ["exposure_score"] + COMPONENTS
    summary = (
        df.dropna(subset=[level])
        .groupby(level)[cols]
        .mean()
        .sort_values("exposure_score", ascending=False)
        .round(2)
    )
    # Which component stands highest on average tells you what drives the group.
    summary["top_driver"] = summary[COMPONENTS].idxmax(axis=1)

    print(summary.to_string())

    stem = "regional" if level == "region" else "division"
    summary.to_csv(f"outputs/{stem}_summary.csv")

    order = summary.index[::-1]
    height = 3.4 if level == "region" else 0.5 * len(order) + 1.0
    fig, ax = plt.subplots(figsize=(7, height))
    ax.barh(order, summary.loc[order, "exposure_score"], color="#c14625")
    ax.set_xlabel("Average exposure score")
    ax.set_title(f"Average exposure by US Census {level}")
    for i, v in enumerate(summary.loc[order, "exposure_score"]):
        ax.text(v + 0.6, i, f"{v:.0f}", va="center", fontsize=8)
    ax.margins(x=0.12)
    fig.tight_layout()
    fig.savefig(f"outputs/{stem}_exposure.png", dpi=130)
    plt.close(fig)

    print(f"\nwrote outputs/{stem}_summary.csv and outputs/{stem}_exposure.png")


if __name__ == "__main__":
    main()
