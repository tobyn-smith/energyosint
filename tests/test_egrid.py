"""Checks on the eGRID plant loader, against a workbook shaped like the real one.

eGRID puts a banner row above the real header and mixes retired plants in with
running ones, so the loader has to skip the first row and drop anything without
usable capacity. These build a miniature version of that sheet.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from grid import sources


def _cfg(path):
    return {"sources": {"plants_workbook": str(path), "allow_synthetic_fallback": True,
                        "cache_raw": False, "eia_api_base": "x"}}


def _write_workbook(path: Path, sheet="PLNT23") -> Path:
    """A tiny sheet with eGRID's layout: a banner row, then the real header."""
    rows = [
        ["PSTATABB", "PNAME", "PLFUELCT", "NAMEPCAP"],
        ["GA", "Vogtle", "NUCLEAR", 3544.0],
        ["GA", "Bowen", "COAL", 3499.0],
        ["GA", "Some Gas Plant", "GAS", 500.0],
        ["WV", "A Coal Plant", "COAL", 1000.0],
        ["WV", "Retired Thing", "COAL", 0.0],        # zero capacity, should go
        ["WV", "Planned Thing", "GAS", None],        # no capacity, should go
        ["ZZ", "Not A State", "GAS", 900.0],         # not one of our 51
    ]
    frame = pd.DataFrame(rows)
    with pd.ExcelWriter(path) as writer:
        # header=1 in the loader means one banner row sits above the real header
        pd.DataFrame([["eGRID2023 Plant file"]]).to_excel(
            writer, sheet_name=sheet, index=False, header=False)
        frame.to_excel(writer, sheet_name=sheet, index=False, header=False, startrow=1)
    return path


def test_reads_state_fuel_and_capacity(tmp_path):
    book = _write_workbook(tmp_path / "egrid2023.xlsx")
    out = sources._egrid_plants(_cfg(book))
    assert out is not None
    assert set(out.columns) == {"state", "plant_name", "fuel", "capacity_mw", "source"}
    assert set(out["state"]) == {"GA", "WV"}
    assert out["source"].unique().tolist() == ["egrid"]
    vogtle = out[out["plant_name"] == "Vogtle"].iloc[0]
    assert vogtle["capacity_mw"] == 3544.0
    assert vogtle["fuel"] == "nuclear"


def test_drops_retired_and_out_of_scope_rows(tmp_path):
    book = _write_workbook(tmp_path / "egrid2023.xlsx")
    out = sources._egrid_plants(_cfg(book))
    names = set(out["plant_name"])
    assert "Retired Thing" not in names       # zero capacity
    assert "Planned Thing" not in names       # no capacity at all
    assert "Not A State" not in names         # ZZ is not in our 51
    assert len(out) == 4


def test_gas_is_renamed_to_match_the_other_sources(tmp_path):
    book = _write_workbook(tmp_path / "egrid2023.xlsx")
    out = sources._egrid_plants(_cfg(book))
    # eGRID calls it GAS; the rest of the project calls it natural_gas
    assert "natural_gas" in set(out["fuel"])
    assert "gas" not in set(out["fuel"])


def test_missing_file_falls_back_quietly(tmp_path):
    assert sources._egrid_plants(_cfg(tmp_path / "nope.xlsx")) is None


def test_workbook_without_a_plant_sheet_is_refused(tmp_path):
    odd = tmp_path / "other.xlsx"
    pd.DataFrame({"a": [1]}).to_excel(odd, sheet_name="Summary", index=False)
    assert sources._egrid_plants(_cfg(odd)) is None


def test_the_loader_feeds_the_scorer(tmp_path):
    """The whole point: eGRID output must be usable by cleaning and scoring."""
    from grid import cleaning, scoring
    book = _write_workbook(tmp_path / "egrid2023.xlsx")
    plants = sources._egrid_plants(_cfg(book))
    rel = pd.DataFrame({"state": ["GA", "WV"], "saidi_minutes": [343.0, 752.0],
                        "saifi_events": [1.4, 1.9]})
    dem = pd.DataFrame({"state": ["GA", "WV"], "peak_demand_mw": [4000.0, 800.0],
                        "net_generation_gwh": [20000.0, 4000.0]})
    table = cleaning.build_state_table(plants, rel, dem)
    assert len(table) == 2
    scored = scoring.score(table, {"outage_burden": 0.45, "infra_concentration": 0.30,
                                   "exposure_deficit": 0.25})
    assert len(scored) == 2
    # WV is all coal here, so it must look more concentrated than mixed-fuel GA.
    hhi = table.set_index("state")["fuel_hhi"]
    assert hhi["WV"] > hhi["GA"]


if __name__ == "__main__":
    print("run with: pytest tests/test_egrid.py")
