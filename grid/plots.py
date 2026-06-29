"""Output visuals. Always writes the ranked bar chart; adds a choropleth if
geopandas + a boundary file happen to be available."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt


def ranked_bar(scored, top_n: int, out_path: Path) -> Path:
    top = scored.head(top_n).iloc[::-1]   # reverse so #1 lands at the top

    fig, ax = plt.subplots(figsize=(8, 0.42 * len(top) + 1))
    ax.barh(top["state"], top["exposure_score"], color="#b5462f")
    ax.set_xlabel("Exposure score (0-100)")
    ax.set_title(f"Most exposed states — grid resilience index (top {top_n})")
    for y, v in zip(range(len(top)), top["exposure_score"]):
        ax.text(v + 0.6, y, f"{v:.0f}", va="center", fontsize=8)
    ax.margins(x=0.08)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


def choropleth(scored, out_path: Path) -> Path | None:
    """State map, only if geopandas is installed. Returns None otherwise."""
    try:
        import geopandas as gpd
    except ImportError:
        return None

    # Natural Earth admin-1 ships with most geopandas installs via this URL;
    # if it's offline we just skip the map rather than fail the run.
    try:
        url = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_1_states_provinces.zip"
        states = gpd.read_file(url)
    except Exception:
        return None

    states = states[states["iso_3166_2"].str.startswith("US-", na=False)].copy()
    states["state"] = states["iso_3166_2"].str.replace("US-", "", regex=False)
    merged = states.merge(scored[["state", "exposure_score"]], on="state", how="left")

    ax = merged.plot(
        column="exposure_score", cmap="OrRd", legend=True,
        edgecolor="white", linewidth=0.3, missing_kwds={"color": "lightgrey"},
        figsize=(11, 6.5),
    )
    ax.set_axis_off()
    ax.set_title("Grid resilience exposure index by state")
    ax.set_xlim(-128, -65)
    ax.set_ylim(23, 50)   # crop to CONUS; AK/HI sit far off and squash the rest
    ax.figure.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(ax.figure)
    return out_path
