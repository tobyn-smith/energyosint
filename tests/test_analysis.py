"""Checks on the analysis helper scripts, so a change does not quietly break the
ranking sensitivity table or the findings summary."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

from grid import scoring
import weight_sensitivity as ws
import report

# Three states, each worst on exactly one component (same shape as the scoring tests).
TINY = pd.DataFrame({
    "state": ["A", "B", "C"],
    "saidi_minutes": [900.0, 100.0, 100.0],
    "saifi_events": [3.0, 1.0, 1.0],
    "fuel_hhi": [3000.0, 9000.0, 3000.0],
    "top_plant_share": [0.2, 0.9, 0.2],
    "capacity_margin": [1.5, 1.5, 1.0],
    "n_fuels": [4, 1, 1],
})

WEIGHTINGS = {
    "even": {"outage_burden": 1 / 3, "infra_concentration": 1 / 3, "exposure_deficit": 1 / 3},
    "outage_heavy": {"outage_burden": 0.6, "infra_concentration": 0.2, "exposure_deficit": 0.2},
}


def test_rank_under_weightings_returns_one_column_per_weighting():
    ranks = ws.rank_under_weightings(TINY, WEIGHTINGS, normalize="zscore")
    assert list(ranks.columns) == ["even", "outage_heavy"]
    assert set(ranks.index) == {"A", "B", "C"}


def test_rank_under_weightings_honours_the_normalize_argument():
    # The whole point of the fix: the helper must score under the normalization it
    # is handed, matching what scoring.score does directly, not a hardcoded one.
    direct = scoring.score(TINY, WEIGHTINGS["even"], normalize="minmax")
    direct = direct.set_index("state")["rank"].to_dict()
    via_helper = ws.rank_under_weightings(TINY, WEIGHTINGS, normalize="minmax")["even"].to_dict()
    assert via_helper == direct


def test_report_uses_the_actual_state_count(tmp_path, monkeypatch):
    idx = tmp_path / "exposure_index.csv"
    pd.DataFrame({
        "rank": [1, 2, 3],
        "state": ["GA", "WV", "ME"],
        "exposure_score": [80.0, 60.0, 40.0],
        "driver": ["outage_burden", "infra_concentration", "exposure_deficit"],
    }).to_csv(idx, index=False)

    monkeypatch.setattr(report, "INDEX", idx)
    monkeypatch.setattr(report, "OUT", tmp_path / "findings.md")
    monkeypatch.setattr(report, "RAW", tmp_path / "no_raw_dir")

    report.main()
    text = (tmp_path / "findings.md").read_text(encoding="utf-8")
    assert "Across the 3 states" in text
    assert "Across the 51 states" not in text
