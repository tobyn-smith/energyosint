"""Checks on the live EIA plants pull (_live_plants).

EIA-860M is a monthly snapshot of every generator in the country, so one page
never holds it all and the history repeats every plant once per month. The
loader must walk the pages with offset and then keep only the newest period, or
capacity totals quietly come out partial (page 1 only) or doubled (all months).
These simulate the endpoint and check both.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from grid import sources


def _fake_plant(period: str, state: str, plant: str, fuel: str, mw: float) -> dict:
    # Field names as the EIA v2 API returns them for this dataset.
    return {
        "period": period,
        "stateid": state,
        "plantName": plant,
        "energy_source_desc": fuel,
        "nameplate-capacity-mw": mw,
    }


def test_walks_all_pages_and_keeps_latest_period(monkeypatch):
    # 6,004 rows across two months, shaped like the real endpoint: newest month
    # first, more than one page of 5,000.
    history = [_fake_plant("2023-12", "GA", f"GA-{i:04d}", "Natural Gas", 100.0)
               for i in range(4000)]
    history += [_fake_plant("2023-11", "GA", f"GA-{i:04d}", "Natural Gas", 100.0)
                for i in range(2000)]
    history += [_fake_plant("2023-12", "ME", "ME-1", "Hydro", 50.0)]
    history += [_fake_plant("2023-11", "ME", "ME-1", "Hydro", 50.0)]

    calls = []

    def fake_get(url, params):
        calls.append(params)
        start = params.get("offset", 0)
        length = params["length"]
        return {"response": {"data": history[start:start + length]}}

    monkeypatch.setattr(sources, "_get_json", fake_get)
    out = sources._live_plants("https://api.eia.gov/v2", "key")

    assert len(calls) == 2, "should have walked both pages, not stopped at 5,000 rows"
    assert calls[0]["offset"] == 0
    assert calls[1]["offset"] == 5000

    assert out is not None
    # Only the newest month survives, so the GA history is not counted twice.
    ga = out[out["state"] == "GA"]["capacity_mw"].sum()
    assert ga == pytest.approx(4000 * 100.0)
    assert set(out["state"]) == {"GA", "ME"}
    me = out[out["state"] == "ME"].iloc[0]
    assert me["capacity_mw"] == pytest.approx(50.0)
    assert me["fuel"] == "hydro"          # lowercased like the eGRID path
    assert out["source"].unique().tolist() == ["eia"]


def test_single_page_works_without_repeating(monkeypatch):
    history = [_fake_plant("2024-01", "TX", "TX-1", "Wind", 200.0)]
    monkeypatch.setattr(
        sources, "_get_json",
        lambda url, params: {"response": {"data": history}},
    )
    out = sources._live_plants("https://api.eia.gov/v2", "key")
    assert out is not None
    assert out["capacity_mw"].sum() == pytest.approx(200.0)


def test_failed_pages_fall_back_to_none(monkeypatch):
    monkeypatch.setattr(sources, "_get_json", lambda url, params: None)
    assert sources._live_plants("https://api.eia.gov/v2", "key") is None
