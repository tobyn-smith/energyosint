"""Output visuals. Always writes the ranked bar chart; adds a choropleth if
geopandas + a boundary file happen to be available."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt


def ranked_bar(scored, top_n: int, out_path: Path) -> Path:
    top = scored.head(top_n).iloc[::-1]   # reverse so #1 lands at the top

    fig, ax = plt.subplots(figsize=(8, 0.42 * len(top) + 1))
    ax.barh(top["state"], top["exposure_score"], color="#b5462f")
    ax.set_xlabel("Exposure score (0 to 100)")
    ax.set_title(f"Most exposed states, grid resilience index (top {top_n})")
    for y, v in zip(range(len(top)), top["exposure_score"]):
        ax.text(v + 0.6, y, f"{v:.0f}", va="center", fontsize=8)
    ax.margins(x=0.08)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


def choropleth(scored, out_path: Path, gpkg_path: Path | None = None) -> Path | None:
    """State map, only if geopandas is installed. Returns None otherwise.

    Also drops a GeoPackage of the scores joined to real (un-moved) state
    geometry, so the result can be opened in QGIS or ArcGIS.
    """
    try:
        import geopandas as gpd
    except ImportError:
        return None

    # Natural Earth admin-1 boundaries. If we can't reach them, skip the map
    # rather than failing the whole run.
    try:
        url = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_1_states_provinces.zip"
        states = gpd.read_file(url)
    except Exception:
        return None

    states = states[states["iso_3166_2"].str.startswith("US-", na=False)].copy()
    states["state"] = states["iso_3166_2"].str.replace("US-", "", regex=False)
    states = states.merge(scored[["state", "exposure_score"]], on="state", how="left")

    # Save the true-geography version before we shuffle Alaska and Hawaii around.
    if gpkg_path is not None:
        states.to_file(gpkg_path, driver="GPKG")

    framed = _with_ak_hi_insets(states)
    ax = framed.plot(
        column="exposure_score", cmap="OrRd", legend=True,
        edgecolor="white", linewidth=0.3, missing_kwds={"color": "lightgrey"},
        legend_kwds={"label": "Exposure (0 to 100)", "shrink": 0.55},
        figsize=(11, 7),
    )
    ax.set_axis_off()
    ax.set_title("Grid resilience exposure index by state")
    ax.figure.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(ax.figure)
    return out_path


def _with_ak_hi_insets(states):
    """Tuck Alaska and Hawaii under the lower 48 so all states fit one frame."""
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import box

    states = states.copy()
    # Alaska's western Aleutians cross the date line and smear once projected,
    # so trim them off before doing anything else.
    ak = states["state"] == "AK"
    if ak.any():
        states.loc[ak, "geometry"] = gpd.clip(states[ak], box(-180, 50, -129, 72)).geometry.values

    proj = states.to_crs(9311)            # equal-area; safe to scale and shift
    conus = proj[~proj["state"].isin(["AK", "HI"])]
    minx, miny, _, maxy = conus.total_bounds
    height = maxy - miny

    # (scale, target lower-left x, target lower-left y) for each inset.
    placements = {
        "AK": (0.40, minx, miny - 0.55 * height),
        "HI": (1.20, minx + 1_300_000, miny - 0.40 * height),
    }
    pieces = [conus]
    for code, (factor, tx, ty) in placements.items():
        sub = proj[proj["state"] == code]
        if sub.empty:
            continue
        moved = sub.geometry.scale(factor, factor, origin="center")
        b = moved.total_bounds
        moved = moved.translate(xoff=tx - b[0], yoff=ty - b[1])
        sub = sub.copy()
        sub["geometry"] = moved.values
        pieces.append(sub)

    return gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs=proj.crs)
