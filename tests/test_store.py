"""Round-trip checks on the SQLite store: a saved run comes back the same."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from grid import cleaning, scoring, sources, store

CFG = {"sources": {"cache_raw": False, "allow_synthetic_fallback": True, "eia_api_base": "x"}}
WEIGHTS = {"outage_burden": 0.45, "infra_concentration": 0.30, "exposure_deficit": 0.25}


def _pipeline_frames():
    plants = sources.load_plants(CFG)
    rel = sources.load_reliability(CFG)
    dem = sources.load_demand(CFG, plants)
    table = cleaning.build_state_table(plants, rel, dem)
    scored = scoring.score(table, WEIGHTS)
    return scored, table


def test_save_and_reload(tmp_path):
    scored, table = _pipeline_frames()
    conn = store.connect(tmp_path / "t.db")
    run_id = store.save_run(conn, scored, table, source="synthetic",
                            normalize="zscore", created_at="2020-01-01T00:00:00+00:00")

    assert store.latest_run_id(conn) == run_id
    back = store.load_scores(conn, run_id)
    assert len(back) == len(scored) == 51
    # ranking order preserved and the top state matches
    assert list(back["rank"]) == sorted(back["rank"])
    assert back.iloc[0]["state"] == scored.sort_values("rank").iloc[0]["state"]

    inputs = store.load_inputs(conn, run_id)
    assert len(inputs) == 51
    assert "saidi_minutes" in inputs.columns
    conn.close()


def test_two_runs_are_independent(tmp_path):
    scored, table = _pipeline_frames()
    conn = store.connect(tmp_path / "t.db")
    r1 = store.save_run(conn, scored, table, source="synthetic",
                        normalize="zscore", created_at="2020-01-01T00:00:00+00:00")
    r2 = store.save_run(conn, scored, table, source="synthetic",
                        normalize="minmax", created_at="2020-01-02T00:00:00+00:00")
    assert r2 != r1
    assert store.latest_run_id(conn) == r2
    assert len(store.list_runs(conn)) == 2
    assert len(store.load_scores(conn, r1)) == 51  # first run still intact
    conn.close()


if __name__ == "__main__":
    import tempfile
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
            print("ok", name)
    print("all passed")
