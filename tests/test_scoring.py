"""quick checks on the scoring, so a change doesn't quietly break the ranking.

runs with pytest, or on its own: python tests/test_scoring.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from grid import cleaning, scoring, sources

CFG = {"sources": {"cache_raw": False, "allow_synthetic_fallback": True, "eia_api_base": "x"}}
WEIGHTS = {"outage_burden": 0.45, "infra_concentration": 0.30, "exposure_deficit": 0.25}


def _scored():
    plants = sources.load_plants(CFG)
    rel = sources.load_reliability(CFG)
    dem = sources.load_demand(CFG, plants)
    table = cleaning.build_state_table(plants, rel, dem)
    return scoring.score(table, WEIGHTS)


def test_one_row_per_state():
    assert len(_scored()) == 51


def test_scores_stay_in_range():
    score = _scored()["exposure_score"]
    assert score.min() >= 0
    assert score.max() <= 100


def test_ranks_are_unique_and_contiguous():
    rank = _scored()["rank"]
    assert rank.is_unique
    assert sorted(rank) == list(range(1, len(rank) + 1))


def test_no_missing_scores():
    assert not _scored()["exposure_score"].isna().any()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all passed")
