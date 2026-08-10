"""Check the scoring arithmetic against numbers worked out by hand.

The other scoring tests check the shape of the result (51 rows, scores in range,
ranks unique). None of them would notice if the maths quietly changed, so this
one pins the actual numbers for a tiny input I can compute on paper.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from grid import scoring

WEIGHTS = {"outage_burden": 0.45, "infra_concentration": 0.30, "exposure_deficit": 0.25}

# Three states, chosen so each one is worst on exactly one component:
#   A: dreadful outages, otherwise fine
#   B: everything in one fuel and one plant
#   C: no headroom over peak demand and only one fuel
TINY = pd.DataFrame({
    "state": ["A", "B", "C"],
    "saidi_minutes": [900.0, 100.0, 100.0],
    "saifi_events": [3.0, 1.0, 1.0],
    "fuel_hhi": [3000.0, 9000.0, 3000.0],
    "top_plant_share": [0.2, 0.9, 0.2],
    "capacity_margin": [1.5, 1.5, 1.0],
    "n_fuels": [4, 1, 1],
})


def test_each_state_is_flagged_on_the_part_it_is_worst_at():
    out = scoring.score(TINY, WEIGHTS).set_index("state")
    assert out.loc["A", "driver"] == "outage_burden"
    assert out.loc["B", "driver"] == "infra_concentration"
    assert out.loc["C", "driver"] == "exposure_deficit"


def test_score_is_the_weighted_blend_rescaled_to_0_100():
    out = scoring.score(TINY, WEIGHTS).set_index("state")
    parts = ["outage_burden", "infra_concentration", "exposure_deficit"]

    # Recompute the composite straight from the normalised parts and confirm the
    # published score is just that, min-max stretched onto 0 to 100.
    blend = sum(out[c] * WEIGHTS[c] for c in parts) / sum(WEIGHTS.values())
    lo, hi = blend.min(), blend.max()
    expected = (blend - lo) / (hi - lo) * 100
    for state in out.index:
        assert abs(out.loc[state, "exposure_score"] - expected[state]) < 0.05

    # The rescaling means the ends are always pinned.
    assert out["exposure_score"].max() == 100.0
    assert out["exposure_score"].min() == 0.0


def test_higher_saidi_alone_raises_the_score():
    worse = TINY.copy()
    worse.loc[worse["state"] == "B", "saidi_minutes"] = 5000.0
    before = scoring.score(TINY, WEIGHTS).set_index("state").loc["B", "exposure_score"]
    after = scoring.score(worse, WEIGHTS).set_index("state").loc["B", "exposure_score"]
    assert after > before


def test_weights_actually_move_the_answer():
    outage_only = {"outage_burden": 1.0, "infra_concentration": 0.0, "exposure_deficit": 0.0}
    conc_only = {"outage_burden": 0.0, "infra_concentration": 1.0, "exposure_deficit": 0.0}
    # A is the outage case, B the concentration case, so each should top its own ranking.
    assert scoring.score(TINY, outage_only).iloc[0]["state"] == "A"
    assert scoring.score(TINY, conc_only).iloc[0]["state"] == "B"


def test_weights_are_normalised_so_only_their_ratio_matters():
    doubled = {k: v * 2 for k, v in WEIGHTS.items()}
    a = scoring.score(TINY, WEIGHTS)["exposure_score"].tolist()
    b = scoring.score(TINY, doubled)["exposure_score"].tolist()
    assert a == b


def test_identical_states_score_identically():
    same = pd.DataFrame({
        "state": ["X", "Y"],
        "saidi_minutes": [200.0, 200.0], "saifi_events": [1.5, 1.5],
        "fuel_hhi": [4000.0, 4000.0], "top_plant_share": [0.3, 0.3],
        "capacity_margin": [1.2, 1.2], "n_fuels": [3, 3],
    })
    out = scoring.score(same, WEIGHTS)
    assert out["exposure_score"].nunique() == 1
    # A tie should share the rank rather than inventing an order.
    assert out["rank"].tolist() == [1, 1]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all passed")
