"""How much does the ranking depend on the weights?

The composite weights are a judgement call, so this re-scores the states under a
few alternative weightings and checks how steady the top of the table is. Run
the main pipeline first so data/interim/state_table.csv exists.

    python analysis/weight_sensitivity.py
"""

import sys
from pathlib import Path

import pandas as pd

# let the script find the grid package when run from the analysis folder
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grid import scoring

STATE_TABLE = Path("data/interim/state_table.csv")

# A handful of defensible weightings, including the default from config.yaml.
weightings = {
    "default":         {"outage_burden": 0.45, "infra_concentration": 0.30, "exposure_deficit": 0.25},
    "even":            {"outage_burden": 1/3,  "infra_concentration": 1/3,  "exposure_deficit": 1/3},
    "outage_heavy":    {"outage_burden": 0.60, "infra_concentration": 0.20, "exposure_deficit": 0.20},
    "structure_heavy": {"outage_burden": 0.20, "infra_concentration": 0.40, "exposure_deficit": 0.40},
}


def main():
    if not STATE_TABLE.exists():
        raise SystemExit("run `python pipeline.py` first, the state table is missing")

    table = pd.read_csv(STATE_TABLE)

    ranks = {}
    for name, w in weightings.items():
        scored = scoring.score(table, weights=w, normalize="zscore")
        ranks[name] = scored.set_index("state")["rank"]
    ranks = pd.DataFrame(ranks)

    in_top10 = ranks <= 10
    hits = in_top10.sum(axis=1)
    steady = sorted(hits[hits == len(weightings)].index)
    movers = ranks[in_top10.any(axis=1) & (hits < len(weightings))].sort_values("default")

    print(f"Top 10 under all {len(weightings)} weightings:")
    print("  " + ", ".join(steady))
    print("\nIn the top 10 under some weightings but not others:")
    print(movers.to_string())

    ranks.sort_values("default").to_csv("outputs/rank_sensitivity.csv")
    print("\nwrote outputs/rank_sensitivity.csv")


if __name__ == "__main__":
    main()
