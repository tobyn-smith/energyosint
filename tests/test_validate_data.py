"""Checks on the published-data validator: it must pass real pipeline output and
catch the ways the committed figures could go wrong (drift, corruption, editing)."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

from grid import cleaning, scoring, sources
import pipeline
import validate_data as vd

CFG = {"sources": {"cache_raw": False, "allow_synthetic_fallback": True, "eia_api_base": "x"}}
WEIGHTS = {"outage_burden": 0.45, "infra_concentration": 0.30, "exposure_deficit": 0.25}
KEEP = [
    "rank", "state", "exposure_score", "driver",
    "outage_burden", "infra_concentration", "exposure_deficit",
    "saidi_minutes", "fuel_hhi", "top_plant_share", "capacity_margin",
]


def _write_dataset(dirpath: Path):
    """A full 51-state dataset straight from the pipeline's own code, so the CSV
    and the site JSON are genuinely self-consistent to begin with."""
    plants = sources.load_plants(CFG)
    rel = sources.load_reliability(CFG)
    dem = sources.load_demand(CFG, plants)
    table = cleaning.build_state_table(plants, rel, dem)
    scored = scoring.score(table, WEIGHTS)

    csv = dirpath / "exposure_index.csv"
    scored[KEEP].to_csv(csv, index=False)
    site = dirpath / "index.json"
    pipeline.write_site_json(scored, site)
    cfg = dirpath / "config.yaml"
    cfg.write_text(
        "weights:\n  outage_burden: 0.45\n  infra_concentration: 0.30\n"
        "  exposure_deficit: 0.25\nscoring:\n  normalize: zscore\n",
        encoding="utf-8",
    )
    return csv, site, cfg


@pytest.fixture()
def good(tmp_path, monkeypatch):
    csv, site, cfg = _write_dataset(tmp_path)
    monkeypatch.setattr(vd, "CSV", csv)
    monkeypatch.setattr(vd, "SITE", site)
    monkeypatch.setattr(vd, "CONFIG", cfg)
    return csv, site, cfg


def test_passes_on_real_pipeline_output(good):
    vd.validate()  # must not raise


def test_catches_a_fabricated_score(good):
    csv, _, _ = good
    df = pd.read_csv(csv)
    df.loc[df["state"] == "GA", "exposure_score"] = 12.3   # typed in, not computed
    df.to_csv(csv, index=False)
    with pytest.raises(vd.DataError, match="not reproducible"):
        vd.validate()


def test_catches_an_out_of_range_score(good):
    csv, _, _ = good
    df = pd.read_csv(csv)
    df.loc[df["state"] == "GA", "exposure_score"] = 250.0
    df.to_csv(csv, index=False)
    with pytest.raises(vd.DataError):
        vd.validate()


def test_catches_drift_between_the_two_files(good):
    csv, site, _ = good
    rows = json.loads(site.read_text())
    rows[0]["o"] = rows[0]["o"] + 5.0   # site now disagrees with the csv
    site.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(vd.DataError, match="disagrees between files"):
        vd.validate()


def test_catches_a_missing_state(good):
    csv, _, _ = good
    df = pd.read_csv(csv)
    df = df[df["state"] != "GA"]
    df.to_csv(csv, index=False)
    with pytest.raises(vd.DataError):
        vd.validate()


def test_catches_a_bad_state_code(good):
    csv, _, _ = good
    df = pd.read_csv(csv)
    df.loc[df["state"] == "GA", "state"] = "ZZ"
    df.to_csv(csv, index=False)
    with pytest.raises(vd.DataError, match="not in the 50 states"):
        vd.validate()
