"""End-to-end checks on the JSON API, against a seeded temporary database."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
from grid import cleaning, scoring, sources, store

CFG = {"sources": {"cache_raw": False, "allow_synthetic_fallback": True, "eia_api_base": "x"}}
WEIGHTS = {"outage_burden": 0.45, "infra_concentration": 0.30, "exposure_deficit": 0.25}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    plants = sources.load_plants(CFG)
    rel = sources.load_reliability(CFG)
    dem = sources.load_demand(CFG, plants)
    table = cleaning.build_state_table(plants, rel, dem)
    scored = scoring.score(table, WEIGHTS)

    db = tmp_path / "api.db"
    conn = store.connect(db)
    store.save_run(conn, scored, table, source="synthetic",
                   normalize="zscore", created_at="2020-01-01T00:00:00+00:00")
    conn.close()

    monkeypatch.setattr(server, "_db_path", lambda: str(db))
    return TestClient(server.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["runs"] >= 1


def test_states_list(client):
    r = client.get("/api/states")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 51
    assert {"state", "name", "exposure_score", "rank", "driver"} <= set(body[0])


def test_one_state(client):
    r = client.get("/api/states/ga")   # case-insensitive
    assert r.status_code == 200
    assert r.json()["name"] == "Georgia"

    missing = client.get("/api/states/ZZ")
    assert missing.status_code == 404


def test_score_reweights(client):
    # All weight on outages puts Georgia top on the sample data.
    r = client.get("/api/score", params={"wO": 100, "wC": 0, "wD": 0, "top": 3})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    assert body[0]["state"] == "GA"
    assert body[0]["rank"] == 1


def test_score_rejects_bad_weights(client):
    assert client.get("/api/score", params={"wO": 0, "wC": 0, "wD": 0}).status_code == 400
    assert client.get("/api/score", params={"wO": -1, "wC": 1, "wD": 1}).status_code == 400


def test_regions(client):
    r = client.get("/api/regions", params={"level": "region"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 4
    assert {"region", "exposure_score", "top_driver"} <= set(body[0])
    # sorted by score, highest first
    scores = [row["exposure_score"] for row in body]
    assert scores == sorted(scores, reverse=True)

    div = client.get("/api/regions", params={"level": "division"})
    assert len(div.json()) == 9

    assert client.get("/api/regions", params={"level": "bogus"}).status_code == 422


if __name__ == "__main__":
    print("run with: pytest tests/test_api.py")
