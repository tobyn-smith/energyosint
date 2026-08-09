"""Pull the ranking into one readable summary, written to outputs/findings.md.

Reads the scored table and writes a short markdown report: the most and least
exposed states, the main driver behind each of the top ones, a rough split of
what drives exposure across the country, and the usual caveats. Run the pipeline
first so outputs/exposure_index.csv exists.

    python analysis/report.py
"""

import sys
from pathlib import Path

import pandas as pd

# let the script find the grid package when run from the analysis folder
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grid.regions import STATE_NAMES

INDEX = Path("outputs/exposure_index.csv")
OUT = Path("outputs/findings.md")

DRIVERS = {
    "outage_burden": "outage burden",
    "infra_concentration": "concentration",
    "exposure_deficit": "the exposure deficit",
}


def main():
    if not INDEX.exists():
        raise SystemExit("run `python pipeline.py` first, outputs/exposure_index.csv is missing")

    df = pd.read_csv(INDEX).sort_values("rank")
    df["name"] = df["state"].map(STATE_NAMES)
    # The pipeline already works out each state's driver; just make it readable.
    df["driver"] = df["driver"].map(DRIVERS)

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

    lines.append("## Reading it for policy")
    lines.append("")
    lines.append("The driver matters more than the rank, because each one points at a different lever:")
    lines.append("")
    lines.append("- Outage burden is a weather and wires problem. The lever is hardening and restoration, not new plants.")
    lines.append("- Concentration is a single-point-of-failure problem. The lever is diversifying what the state leans on.")
    lines.append("- An exposure deficit is a headroom problem. The lever is capacity, storage or demand-side work.")
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
