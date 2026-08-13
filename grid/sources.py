"""Data ingestion.

Three public inputs, each with a live EIA path and a synthetic fallback:

  - plant-level generation capacity (EIA-860)
  - state reliability metrics, SAIDI / SAIFI (EIA-861)
  - state peak demand and net generation

Live pulls need a free EIA API key in EIA_API_KEY. When that's missing or a
request fails, we generate a deterministic stand-in so the rest of the
pipeline still has something to chew on. The fallback is clearly labelled in
the output (`source` column) so nobody mistakes it for the real thing.
"""

from __future__ import annotations

import io
import os
import zipfile
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import requests

RAW_DIR = Path("data/raw")

# 50 states + DC. PR/territories left out because EIA reliability coverage is
# patchy there and it would skew the normalization.
STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
]

FUELS = ["natural_gas", "coal", "nuclear", "hydro", "wind", "solar", "oil"]


def _seed_for(label: str) -> int:
    """Stable per-state seed so synthetic runs are reproducible."""
    return zlib.adler32(label.encode()) & 0xFFFFFFFF


def _eia_key() -> str | None:
    key = os.environ.get("EIA_API_KEY", "").strip()
    return key or None


def _get_json(url: str, params: dict) -> dict | None:
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Synthetic fallbacks
# --------------------------------------------------------------------------- #

# Rough regional fuel leanings so the sample isn't uniform noise. Not meant to
# be accurate per state, just plausible enough to exercise the scoring.
_FUEL_BIAS = {
    "coal": {"WV", "WY", "KY", "ND", "MT", "IN", "MO"},
    "nuclear": {"IL", "PA", "SC", "TN", "NH"},
    "hydro": {"WA", "OR", "ID", "NY"},
    "wind": {"IA", "KS", "OK", "TX", "ND", "SD"},
    "solar": {"CA", "NV", "AZ", "NC"},
}


def _plant_count(rng: np.random.Generator) -> int:
    return int(rng.integers(6, 16))


def _synthetic_plants() -> pd.DataFrame:
    rows = []
    for st in STATES:
        rng = np.random.default_rng(_seed_for("plants:" + st))
        weights = np.ones(len(FUELS))
        for fuel, members in _FUEL_BIAS.items():
            if st in members:
                weights[FUELS.index(fuel)] += 4.0
        weights = weights / weights.sum()

        for i in range(_plant_count(rng)):
            fuel = rng.choice(FUELS, p=weights)
            # Nuclear/coal plants run big; solar/wind sites are smaller and
            # more numerous in reality, but capacity is what we care about.
            base = {"nuclear": 1100, "coal": 700, "natural_gas": 450,
                    "hydro": 300, "wind": 180, "solar": 120, "oil": 90}[fuel]
            cap = max(20.0, rng.normal(base, base * 0.35))
            rows.append({
                "state": st,
                "plant_name": f"{st}-{fuel[:3].upper()}-{i+1:02d}",
                "fuel": fuel,
                "capacity_mw": round(cap, 1),
            })
    df = pd.DataFrame(rows)
    df["source"] = "synthetic"
    return df


def _synthetic_reliability() -> pd.DataFrame:
    rows = []
    for st in STATES:
        rng = np.random.default_rng(_seed_for("rel:" + st))
        # SAIDI in minutes/customer/year. National figures cluster a few
        # hundred minutes with a long storm-driven tail, so lognormal fits.
        saidi = float(rng.lognormal(mean=5.4, sigma=0.55))
        saifi = float(np.clip(rng.normal(1.3, 0.5), 0.3, 4.0))
        rows.append({
            "state": st,
            "saidi_minutes": round(saidi, 1),
            "saifi_events": round(saifi, 2),
        })
    df = pd.DataFrame(rows)
    df["source"] = "synthetic"
    return df


def _synthetic_demand(plants: pd.DataFrame) -> pd.DataFrame:
    cap_by_state = plants.groupby("state")["capacity_mw"].sum()
    rows = []
    for st in STATES:
        rng = np.random.default_rng(_seed_for("dem:" + st))
        cap = float(cap_by_state.get(st, 5000.0))
        # Peak demand as a fraction of installed capacity. Centred below 1 but
        # the tail crosses it, which is exactly the tight-margin case we want
        # the exposure component to catch.
        ratio = float(np.clip(rng.normal(0.82, 0.18), 0.4, 1.25))
        peak = cap * ratio
        rows.append({
            "state": st,
            "peak_demand_mw": round(peak, 1),
            "net_generation_gwh": round(peak * rng.uniform(3.5, 5.5), 0),
        })
    df = pd.DataFrame(rows)
    df["source"] = "synthetic"
    return df


# --------------------------------------------------------------------------- #
# Live EIA pulls (best-effort; fall back on any miss)
# --------------------------------------------------------------------------- #

def _live_plants(base: str, key: str) -> pd.DataFrame | None:
    # EIA-860M operating generator capacity by plant and energy source.
    url = f"{base}/electricity/operating-generator-capacity/data/"
    params = {
        "api_key": key,
        "frequency": "monthly",
        "data[0]": "nameplate-capacity-mw",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    payload = _get_json(url, params)
    try:
        records = payload["response"]["data"]
    except (TypeError, KeyError):
        return None
    if not records:
        return None

    df = pd.DataFrame(records)
    # Field names drift between EIA datasets; map defensively.
    rename = {
        "stateid": "state", "plantName": "plant_name",
        "energy_source_desc": "fuel",
        "nameplate-capacity-mw": "capacity_mw",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df})
    needed = {"state", "fuel", "capacity_mw"}
    if not needed.issubset(df.columns):
        return None

    df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce")
    df = df.dropna(subset=["capacity_mw"])
    df = df[df["state"].isin(STATES)]
    if df.empty:
        return None
    df["plant_name"] = df.get("plant_name", "unknown")
    df["source"] = "eia"
    return df[["state", "plant_name", "fuel", "capacity_mw", "source"]]


def _reliability_sheet(path: Path):
    """Open the EIA-861 reliability workbook, straight or from inside the annual zip.

    EIA ships reliability as Reliability_YYYY.xlsx, usually bundled in f861YYYY.zip.
    Accepting either saves unpacking it by hand. Returns an open file object or a
    path that pandas can read, or None.
    """
    if path.suffix.lower() == ".zip":
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError):
            return None
        for member in zf.namelist():
            if "reliab" in member.lower() and member.lower().endswith((".xlsx", ".xls")):
                return io.BytesIO(zf.read(member))
        return None
    return path


def combined_header(head: pd.DataFrame, header_row: int) -> list[str]:
    """Flatten the workbook's stacked header rows into one name per column.

    Every row above the names is a grouping level, and they matter: the sheet
    repeats the same column names under "IEEE Standard" and again under "Any
    Standard", so only the top row tells the two blocks apart.
    """
    levels = [head.iloc[i].ffill() for i in range(header_row)]
    names = head.iloc[header_row]
    out = []
    for j in range(len(names)):
        parts = [str(lv.iloc[j]).strip().lower() for lv in levels]
        parts = [p for p in parts if p and p != "nan"]
        parts.append(str(names.iloc[j]).strip().lower())
        out.append(" | ".join(parts))
    return out


def _live_reliability(cfg: dict) -> pd.DataFrame | None:
    """State SAIDI and SAIFI from a local EIA-861 reliability workbook, if present.

    EIA publishes this as a spreadsheet rather than through the API, so point
    `sources.reliability_workbook` in config.yaml at a downloaded copy (either
    Reliability_YYYY.xlsx or the f861YYYY.zip it comes in). Returns None on
    anything unexpected so the caller falls back to the sample.

    Two things about the real file are worth knowing. It carries two stacked
    header rows, the upper one naming groups like "All Events (With Major Event
    Days)", so the two are combined before looking for a column. And it already
    has a State Totals sheet, which is what we want: rolling the per-utility sheet
    up by hand would weight a tiny co-op the same as a utility serving millions.

    We take the figures that include major event days, because storms are most of
    what this project is about.
    """
    name = cfg["sources"].get("reliability_workbook", "eia861_reliability.xlsx")
    path = Path(name)
    if not path.is_absolute():
        path = RAW_DIR / path
    if not path.exists():
        return None

    # From here the file exists, so a failure means we could not read something we
    # were asked to read. Say so instead of quietly handing back sample data: a
    # silent fallback here looks exactly like success from the outside.
    src = _reliability_sheet(path)
    if src is None:
        print(f"  [sources] {path.name} has no reliability sheet in it, using the sample instead")
        return None
    try:
        book = pd.ExcelFile(src)
    except ImportError:
        print("  [sources] reading .xlsx needs openpyxl (pip install openpyxl), using the sample instead")
        return None
    except Exception as err:
        print(f"  [sources] could not open {path.name} ({err}), using the sample instead")
        return None

    # Prefer the sheet EIA has already aggregated to states.
    sheet = next((s for s in book.sheet_names if "state" in s.lower() and "total" in s.lower()), None)
    if sheet is None:
        sheet = next((s for s in book.sheet_names if "state" in s.lower()), None)
    if sheet is None:
        return None

    try:
        head = pd.read_excel(book, sheet_name=sheet, header=None, nrows=6)
    except Exception:
        return None

    # Find the row holding the real column names, then fold the group row above it
    # in, so "SAIDI" can be told apart from the same name under another group.
    header_row = None
    for i in range(len(head)):
        joined = " ".join(str(x).lower() for x in head.iloc[i].tolist())
        if "saidi" in joined and "state" in joined:
            header_row = i
            break
    if header_row is None:
        return None

    combined = combined_header(head, header_row)

    try:
        df = pd.read_excel(book, sheet_name=sheet, header=header_row)
    except Exception:
        return None
    if len(combined) != len(df.columns):
        return None
    df.columns = combined

    def _find(*needles: str) -> int | None:
        # by position, because the combined names are not unique
        for i, c in enumerate(combined):
            if all(n in c for n in needles):
                return i
        return None

    state_col = _find("state")
    # Prefer the IEEE-standard series: it is the like-for-like one across
    # utilities. Within it, take the figures including major event days, since
    # storms are most of what this project is about.
    saidi_col = _find("ieee", "with major event", "saidi") or _find("saidi")
    saifi_col = _find("ieee", "with major event", "saifi") or _find("saifi")
    if state_col is None or saidi_col is None or saifi_col is None:
        return None

    out = df.iloc[:, [state_col, saidi_col, saifi_col]].copy()
    out.columns = ["state", "saidi_minutes", "saifi_events"]
    out["state"] = out["state"].astype(str).str.strip().str.upper()
    out = out[out["state"].isin(STATES)]
    # Missing entries come through as "." rather than blank, so coerce and drop.
    for c in ("saidi_minutes", "saifi_events"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["saidi_minutes", "saifi_events"])
    if out.empty:
        return None

    out = out.groupby("state", as_index=False).mean(numeric_only=True)
    out["saidi_minutes"] = out["saidi_minutes"].round(1)
    out["saifi_events"] = out["saifi_events"].round(3)
    out["source"] = "eia861"
    return out


def _live_demand(cfg: dict) -> pd.DataFrame | None:
    """State peak demand from a local file, if one is provided.

    Point `sources.demand_file` in config.yaml at a CSV or spreadsheet, or drop
    one at data/raw/state_peak_demand.csv. It needs a state column and a peak
    demand column (megawatts); a net generation column is used if present, else
    estimated. Column names are matched loosely. Returns None if no usable file
    is found so the caller can fall back.
    """
    name = cfg["sources"].get("demand_file", "state_peak_demand.csv")
    path = Path(name)
    if not path.is_absolute():
        path = RAW_DIR / path
    if not path.exists():
        return None

    try:
        reader = pd.read_excel if path.suffix.lower() in (".xlsx", ".xls") else pd.read_csv
        df = reader(path)
    except Exception as err:
        print(f"  [sources] could not read {path.name} ({err}), using the sample instead")
        return None
    df.columns = [str(c).strip().lower() for c in df.columns]

    def _find(*needles: str) -> str | None:
        for c in df.columns:
            if all(n in c for n in needles):
                return c
        return None

    state_col = _find("state")
    peak_col = _find("peak") or _find("demand")
    if not (state_col and peak_col):
        print(f"  [sources] {path.name} needs a state column and a peak demand column, "
              "using the sample instead")
        return None

    out = pd.DataFrame({"state": df[state_col].astype(str).str.strip().str.upper()})
    out["peak_demand_mw"] = pd.to_numeric(df[peak_col], errors="coerce")

    gen_col = _find("net", "generation") or _find("generation")
    if gen_col:
        out["net_generation_gwh"] = pd.to_numeric(df[gen_col], errors="coerce")
    else:
        # No generation column: leave a clearly-derived stand-in from the peak.
        out["net_generation_gwh"] = (out["peak_demand_mw"] * 4.5).round(0)

    out = out[out["state"].isin(STATES)].dropna(subset=["peak_demand_mw"])
    if out.empty:
        return None
    out["peak_demand_mw"] = out["peak_demand_mw"].round(1)
    out["source"] = "eia"
    return out


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #

def _no_synthetic(cfg: dict, what: str) -> None:
    # Honour allow_synthetic_fallback: if it's off, refuse to quietly hand back
    # sample data. Raise so the caller knows real data wasn't available.
    if not cfg["sources"].get("allow_synthetic_fallback", True):
        raise RuntimeError(f"no live {what} data available and allow_synthetic_fallback is off")


def load_plants(cfg: dict) -> pd.DataFrame:
    # Preference order: the EIA API if a key is set, then EPA's eGRID workbook if
    # it has been downloaded, then the synthetic sample.
    key = _eia_key()
    if key:
        live = _live_plants(cfg["sources"]["eia_api_base"], key)
        if live is not None:
            return _maybe_cache(live, "plants", cfg)
    egrid = _egrid_plants(cfg)
    if egrid is not None:
        return _maybe_cache(egrid, "plants", cfg)
    _no_synthetic(cfg, "capacity")
    return _maybe_cache(_synthetic_plants(), "plants", cfg)


def _egrid_plants(cfg: dict) -> pd.DataFrame | None:
    """Plant capacity by fuel from EPA's eGRID workbook, if it has been downloaded.

    eGRID is the other half of the open-data picture: EPA publishes a row for every
    generating plant in the country with its state, primary fuel category and
    nameplate capacity, which is exactly what the concentration measures need. It
    is a different agency from EIA, so it is also a useful independent source.

    Grab eGRID2023 from https://www.epa.gov/egrid and drop the .xlsx in data/raw.
    Returns None on anything unexpected so the caller can fall back.
    """
    name = cfg["sources"].get("plants_workbook", "egrid2023.xlsx")
    path = Path(name)
    if not path.is_absolute():
        path = RAW_DIR / path
    if not path.exists():
        return None

    # The plant sheet is named for the data year (PLNT23 for eGRID2023), so find it
    # rather than hard-coding, and the real header sits on the second row.
    try:
        book = pd.ExcelFile(path)
    except ImportError:
        print("  [sources] reading .xlsx needs openpyxl (pip install openpyxl), using the sample instead")
        return None
    except Exception as err:
        print(f"  [sources] could not open {path.name} ({err}), using the sample instead")
        return None

    sheet = next((s for s in book.sheet_names if s.upper().startswith("PLNT")), None)
    if sheet is None:
        print(f"  [sources] {path.name} has no plant sheet in it, using the sample instead")
        return None
    try:
        df = pd.read_excel(book, sheet_name=sheet, header=1)
    except Exception as err:
        print(f"  [sources] could not read {sheet} from {path.name} ({err}), using the sample instead")
        return None

    cols = {"PSTATABB": "state", "PNAME": "plant_name",
            "PLFUELCT": "fuel", "NAMEPCAP": "capacity_mw"}
    missing = sorted(set(cols) - set(df.columns))
    if missing:
        print(f"  [sources] {path.name} is missing {', '.join(missing)}, using the sample instead")
        return None

    out = df[list(cols)].rename(columns=cols)
    out["state"] = out["state"].astype(str).str.strip().str.upper()
    out = out[out["state"].isin(STATES)]
    out["capacity_mw"] = pd.to_numeric(out["capacity_mw"], errors="coerce")
    # Retired and proposed plants sit in the sheet with no or zero capacity.
    out = out[out["capacity_mw"] > 0].dropna(subset=["fuel"])
    if out.empty:
        print(f"  [sources] no usable plant rows in {path.name}, using the sample instead")
        return None

    # eGRID's categories are close to ours already; fold them to the same names so
    # the fuel counts line up with the synthetic sample.
    rename_fuel = {"GAS": "natural_gas", "OFSL": "other_fossil", "OTHF": "other"}
    out["fuel"] = out["fuel"].astype(str).str.strip().str.lower()
    out["fuel"] = out["fuel"].replace({k.lower(): v for k, v in rename_fuel.items()})
    out["plant_name"] = out["plant_name"].astype(str).str.strip()
    out["capacity_mw"] = out["capacity_mw"].round(1)
    out["source"] = "egrid"
    return out[["state", "plant_name", "fuel", "capacity_mw", "source"]].reset_index(drop=True)


def load_reliability(cfg: dict) -> pd.DataFrame:
    # EIA-861 reliability has no clean API v2 route; it ships as a bulk workbook.
    # If the user has dropped that workbook in data/raw, parse it; otherwise fall
    # back to the synthetic sample.
    live = _live_reliability(cfg)
    if live is not None:
        return _maybe_cache(live, "reliability", cfg)
    _no_synthetic(cfg, "reliability")
    return _maybe_cache(_synthetic_reliability(), "reliability", cfg)


def load_demand(cfg: dict, plants: pd.DataFrame) -> pd.DataFrame:
    # State peak demand is published in EIA's bulk spreadsheets rather than a tidy
    # API series (the API's hourly demand is keyed by balancing authority, not
    # state). So, like reliability, read a local file if one is provided.
    live = _live_demand(cfg)
    if live is not None:
        return _maybe_cache(live, "demand", cfg)
    _no_synthetic(cfg, "demand")
    return _maybe_cache(_synthetic_demand(plants), "demand", cfg)


def _maybe_cache(df: pd.DataFrame, name: str, cfg: dict) -> pd.DataFrame:
    if cfg["sources"].get("cache_raw"):
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(RAW_DIR / f"{name}.csv", index=False)
    return df
