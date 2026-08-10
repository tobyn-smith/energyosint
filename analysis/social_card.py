"""Draw the link preview card used when the project page gets shared.

Makes a 1200x630 image (the size Open Graph wants) with the title, a short line
about what it is, and the exposure map. Run the pipeline first so the scores
exist, then:

    python analysis/social_card.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grid import plots

INDEX = Path("outputs/exposure_index.csv")
OUT = Path("docs/assets/og.png")

PAPER = "#f6f4ef"
INK = "#17181a"
GRAY = "#64655f"
ACCENT = "#2d4f63"


def main():
    if not INDEX.exists():
        raise SystemExit("run `python pipeline.py` first, outputs/exposure_index.csv is missing")

    try:
        import geopandas as gpd
    except ImportError:
        raise SystemExit("this needs geopandas: pip install geopandas")

    boundary = plots._boundary_file()
    if boundary is None:
        raise SystemExit("could not get the state boundary file, so the card cannot be drawn")

    scores = pd.read_csv(INDEX)
    states = gpd.read_file(boundary)
    states = states[states["iso_3166_2"].str.startswith("US-", na=False)].copy()
    states["state"] = states["iso_3166_2"].str.replace("US-", "", regex=False)
    states = states.merge(scores[["state", "exposure_score"]], on="state", how="left")
    framed = plots._with_ak_hi_insets(states)

    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    fig.patch.set_facecolor(PAPER)

    # Map on the right, text on the left.
    ax = fig.add_axes([0.42, 0.02, 0.60, 0.96])
    framed.plot(ax=ax, column="exposure_score", cmap="OrRd", edgecolor=PAPER,
                linewidth=0.4, missing_kwds={"color": "#ded9d0"})
    ax.set_axis_off()

    fig.text(0.055, 0.78, "Grid Resilience", fontsize=44, color=INK,
             family="serif", weight="bold", va="top")
    fig.text(0.055, 0.645, "Exposure Index", fontsize=44, color=INK,
             family="serif", weight="bold", va="top")
    fig.text(0.055, 0.50, "Which US states look most exposed\nto losing power, and what is\ndriving it.",
             fontsize=19, color=GRAY, family="serif", va="top", linespacing=1.45)
    fig.text(0.055, 0.17, "Built from open EIA data", fontsize=13.5, color=ACCENT,
             family="monospace", va="top")
    fig.text(0.055, 0.10, "Python  ·  R  ·  SQLite  ·  FastAPI", fontsize=12, color=GRAY,
             family="monospace", va="top")

    # a thin rule to anchor the text block
    fig.add_artist(plt.Line2D([0.055, 0.30], [0.245, 0.245], color="#ddd9d0", linewidth=1.2))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor=PAPER)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
