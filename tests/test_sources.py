"""Checks on reading the real EIA-861 reliability workbook.

The real file is awkward in three ways, and each of them is easy to get wrong:
two stacked header rows, the same column names repeated under "IEEE Standard"
and again under "Any Standard", and missing values written as "." rather than
left blank. These build a small workbook with the same shape and check the
loader picks the right numbers out of it, so a fix here does not regress later.
"""

import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from grid import sources

# Column layout copied from Reliability_2023.xlsx, trimmed to what we read.
TOP = ["Characteristics", None, "IEEE Standard", None, None, None, None, None, "Any Standard", None]
GROUP = [None, None, "All Events (With Major Event Days)", None, None, None,
         "Without Major Event Days", None, "All Events (With Major Event Days)", None]
NAMES = ["Data Year", "State", "Number of Customers",
         "SAIDI (minutes per year)", "SAIFI (times per year)", "CAIDI (minutes per year)",
         "SAIDI (minutes per year)", "SAIFI (times per year)",
         "SAIDI (minutes per year)", "SAIFI (times per year)"]

ROWS = [
    # the IEEE with-MED pair is what we want: 342.7 / 1.858
    [2023, "GA", 4600000, 342.7, 1.858, 184.4, 150.1, 1.201, 999.9, 9.999],
    [2023, "ME", 800000, 1863.0, 3.314, 562.1, 300.2, 1.500, 111.1, 1.111],
    [2023, "ZZ", 1000, 500.0, 2.000, 250.0, 100.0, 1.000, 1.0, 1.0],   # not a state
    [2023, "WY", 280000, ".", ".", ".", ".", ".", ".", "."],           # missing marker
]


def _write_workbook(path: Path, sheet_name="State Totals"):
    frame = pd.DataFrame([TOP, GROUP, NAMES] + ROWS)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet_name, header=False, index=False)
    return path


def _cfg(name):
    return {"sources": {"reliability_workbook": str(name), "cache_raw": False,
                        "allow_synthetic_fallback": True, "eia_api_base": "x"}}


def test_reads_the_ieee_with_med_columns(tmp_path):
    book = _write_workbook(tmp_path / "Reliability_2023.xlsx")
    out = sources._live_reliability(_cfg(book))

    assert out is not None, "loader gave up on a workbook shaped like the real one"
    ga = out[out["state"] == "GA"].iloc[0]
    # must be the IEEE / with-major-event-days pair, not the other two blocks
    assert ga["saidi_minutes"] == pytest.approx(342.7)
    assert ga["saifi_events"] == pytest.approx(1.858)
    assert out["source"].unique().tolist() == ["eia861"]


def test_drops_non_states_and_dot_markers(tmp_path):
    book = _write_workbook(tmp_path / "Reliability_2023.xlsx")
    out = sources._live_reliability(_cfg(book))

    assert "ZZ" not in set(out["state"]), "kept a row that is not one of the 51"
    assert "WY" not in set(out["state"]), "kept a row whose values were all '.'"
    assert set(out["state"]) == {"GA", "ME"}


def test_reads_from_inside_the_annual_zip(tmp_path):
    book = _write_workbook(tmp_path / "Reliability_2023.xlsx")
    bundle = tmp_path / "f8612023.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.write(book, "Reliability_2023.xlsx")

    out = sources._live_reliability(_cfg(bundle))
    assert out is not None, "could not find the workbook inside the zip"
    assert out[out["state"] == "GA"].iloc[0]["saidi_minutes"] == pytest.approx(342.7)


def test_missing_file_falls_back_quietly(tmp_path):
    assert sources._live_reliability(_cfg(tmp_path / "nope.xlsx")) is None


def test_unrelated_spreadsheet_is_refused(tmp_path):
    odd = tmp_path / "other.xlsx"
    pd.DataFrame({"a": [1], "b": [2]}).to_excel(odd, index=False)
    assert sources._live_reliability(_cfg(odd)) is None
