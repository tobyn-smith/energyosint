"""Run the whole thing: ingest -> clean -> score -> write outputs.

    python pipeline.py                 # defaults from config.yaml
    python pipeline.py --normalize minmax --top-n 10

Outputs land in data/interim (cleaned table) and outputs/ (scored table +
charts). Set EIA_API_KEY first if you want live capacity data.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from grid import sources, cleaning, scoring, plots

INTERIM = Path("data/interim")
OUTPUTS = Path("outputs")


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
        "rank", "state", "exposure_score",
        "outage_burden", "infra_concentration", "exposure_deficit",
        "saidi_minutes", "fuel_hhi", "top_plant_share", "capacity_margin",
    ]
    scored[keep].to_csv(OUTPUTS / "exposure_index.csv", index=False)

    print("[4/4] plotting")
    bar = plots.ranked_bar(scored, cfg["scoring"]["top_n"], OUTPUTS / "ranked_states.png")
    print(f"      wrote {bar}")
    cmap = plots.choropleth(scored, OUTPUTS / "exposure_map.png",
                            gpkg_path=OUTPUTS / "exposure_states.gpkg")
    print(f"      wrote {cmap} (+ exposure_states.gpkg)" if cmap
          else "      choropleth skipped (geopandas not available)")

    top = scored.head(cfg["scoring"]["top_n"])
    print("\nMost exposed (top of the ranking):")
    print(top[["rank", "state", "exposure_score"]].to_string(index=False))
    if origin == "synthetic":
        print("\nNote: ran on the synthetic fallback. Set EIA_API_KEY for live capacity data.")


def main() -> None:
    p = argparse.ArgumentParser(description="Grid resilience exposure index")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--normalize", choices=["zscore", "minmax"])
    p.add_argument("--top-n", type=int)
    args = p.parse_args()

    cfg = load_config(args.config)
    if args.normalize:
        cfg["scoring"]["normalize"] = args.normalize
    if args.top_n is not None:
        cfg["scoring"]["top_n"] = args.top_n

    run(cfg)


if __name__ == "__main__":
    main()
