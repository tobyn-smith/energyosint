"""Pull the ranking into one readable summary, written to outputs/findings.md.

Reads the scored table and writes a short markdown report: the most and least
exposed states, the main driver behind each of the top ones, a rough split of
what drives exposure across the country, and the usual caveats. Run the pipeline
first so outputs/exposure_index.csv exists.

    python analysis/report.py
"""

from pathlib import Path

import pandas as pd

INDEX = Path("outputs/exposure_index.csv")
OUT = Path("outputs/findings.md")

DRIVERS = {
    "outage_burden": "outage burden",
    "infra_concentration": "concentration",
    "exposure_deficit": "the exposure deficit",
}

NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def main():
    if not INDEX.exists():
        raise SystemExit("run `python pipeline.py` first, outputs/exposure_index.csv is missing")

    df = pd.read_csv(INDEX).sort_values("rank")
    df["name"] = df["state"].map(NAMES)
    df["driver"] = df[list(DRIVERS)].idxmax(axis=1).map(DRIVERS)

    lines = ["# Findings", ""]
    lines.append("Generated from the sample data, so this is illustrative rather than a real result.")
    lines.append("")

    lines.append("## Most exposed states")
    lines.append("")
    for _, r in df.head(10).iterrows():
        lines.append(f"{r['rank']}. {r['name']} ({r['exposure_score']:.1f}), driven mostly by {r['driver']}")
    lines.append("")

    lines.append("## Least exposed")
    lines.append("")
    for _, r in df.tail(5).iterrows():
        lines.append(f"- {r['name']} ({r['exposure_score']:.1f})")
    lines.append("")

    counts = df["driver"].value_counts()
    split = ", ".join(f"{n} by {name}" for name, n in counts.items())
    lines.append("## What tends to drive exposure")
    lines.append("")
    lines.append(f"Across the 51 states, the standout signal is: {split}.")
    lines.append("")

    lines.append("## Caveats")
    lines.append("")
    lines.append("- The numbers are from the sample data, not a live pull.")
    lines.append("- The weights are a judgement call, so the middle of the table shifts if you change them.")
    lines.append("- Concentration and the exposure deficit partly overlap, so the structural side is counted a little twice.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
