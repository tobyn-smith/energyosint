"""Run the whole thing: ingest -> clean -> score -> write outputs.

    python pipeline.py                 # defaults from config.yaml
    python pipeline.py --normalize minmax --top-n 10

Outputs land in data/interim (cleaned table) and outputs/ (scored table +
charts). Set EIA_API_KEY first if you want live capacity data.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from grid import sources, cleaning, scoring, plots, store
from grid.regions import STATE_NAMES

INTERIM = Path("data/interim")
OUTPUTS = Path("outputs")
SITE_DATA = Path("docs/data/index.json")


def write_site_json(scored, path: Path) -> None:
    """The compact per-state array the web deck reads (same shape as its built-in
    fallback): code, name, and the three normalised components."""
    rows = [
        {
            "s": r["state"],
            "n": STATE_NAMES.get(r["state"], r["state"]),
            "o": round(float(r["outage_burden"]), 4),
            "c": round(float(r["infra_concentration"]), 4),
            "d": round(float(r["exposure_deficit"]), 4),
        }
        for _, r in scored.iterrows()
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=0), encoding="utf-8")


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(cfg: dict) -> None:
    for d in (INTERIM, OUTPUTS):
        d.mkdir(parents=True, exist_ok=True)

    print("[1/4] ingesting public data")
    plants = sources.load_plants(cfg)
    reliability = sources.load_reliability(cfg)
    demand = sources.load_demand(cfg, plants)
    origin = plants["source"].iloc[0]
    print(f"      capacity source: {origin} ({len(plants)} plant rows)")

    print("[2/4] building state table")
    state_table = cleaning.build_state_table(plants, reliability, demand)
    state_table.to_csv(INTERIM / "state_table.csv", index=False)
    print(f"      {len(state_table)} states with complete records")

    print("[3/4] scoring")
    scored = scoring.score(
        state_table,
        weights=cfg["weights"],
        normalize=cfg["scoring"]["normalize"],
    )
    keep = [
        "rank", "state", "exposure_score", "driver",
        "outage_burden", "infra_concentration", "exposure_deficit",
        "saidi_minutes", "fuel_hhi", "top_plant_share", "capacity_margin",
    ]
    scored[keep].to_csv(OUTPUTS / "exposure_index.csv", index=False)

    # Persist the run to SQLite and refresh the data file the web deck reads.
    db_path = cfg.get("database", {}).get("path", "outputs/index.db")
    conn = store.connect(db_path)
    run_id = store.save_run(
        conn, scored[keep], state_table,
        source=origin, normalize=cfg["scoring"]["normalize"],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    conn.close()
    print(f"      saved run {run_id} to {db_path}")
    write_site_json(scored, SITE_DATA)
    print(f"      wrote {SITE_DATA}")

    print("[4/4] plotting")
    bar = plots.ranked_bar(scored, cfg["scoring"]["top_n"], OUTPUTS / "ranked_states.png")
    print(f"      wrote {bar}")
    cmap = plots.choropleth(scored, OUTPUTS / "exposure_map.png",
                            gpkg_path=OUTPUTS / "exposure_states.gpkg")
    if cmap:
        print(f"      wrote {cmap} (+ exposure_states.gpkg)")
    else:
        # The map can be skipped for two very different reasons, so say which.
        try:
            import geopandas  # noqa: F401
            print("      map skipped (could not get the boundary file)")
        except ImportError:
            print("      map skipped (geopandas is not installed)")

    top = scored.head(cfg["scoring"]["top_n"])
    print("\nMost exposed (top of the ranking):")
    print(top[["rank", "state", "exposure_score"]].to_string(index=False))
    if origin == "synthetic":
        if os.environ.get("EIA_API_KEY", "").strip():
            print("\nNote: used the synthetic capacity sample. EIA_API_KEY is set, but the live "
                  "pull did not return usable data.")
        else:
            print("\nNote: ran on the synthetic fallback. Set EIA_API_KEY for live capacity data.")


def main() -> None:
    p = argparse.ArgumentParser(description="Grid resilience exposure index")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--normalize", choices=["zscore", "minmax"])
    p.add_argument("--top-n", type=int)
    args = p.parse_args()
    if args.top_n is not None and args.top_n < 1:
        p.error("--top-n must be 1 or more")

    cfg = load_config(args.config)
    if args.normalize:
        cfg["scoring"]["normalize"] = args.normalize
    if args.top_n is not None:
        cfg["scoring"]["top_n"] = args.top_n

    run(cfg)


if __name__ == "__main__":
    main()
