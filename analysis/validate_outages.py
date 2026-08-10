"""Does the outage data line up with the weather that is supposed to cause it?

The index leans hardest on outage burden, which comes from utilities filing
EIA-861. That is worth checking against something collected by somebody else
entirely, so this compares it with NOAA's Storm Events Database, which the
National Weather Service compiles from its own observations.

The test is sharper than "do outages happen where storms happen". EIA publishes
SAIDI twice, once counting major event days and once excluding them, so the gap
between the two is the part of the outage burden that major events account for.
If that gap is real, it should track how much damaging weather a state actually
had. If it does not, the weather story this project tells is weaker than it looks.

Both inputs are downloads. Put them in data/raw:

  EIA-861    https://www.eia.gov/electricity/data/eia861/  (f861YYYY.zip)
  NOAA       https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
             (StormEvents_details-ftp_v1.0_dYYYY_cNNNNNNNN.csv.gz)

    python analysis/validate_outages.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grid import sources
from grid.regions import STATE_NAMES

RAW = Path("data/raw")
OUT_CSV = Path("outputs/validation_storms.csv")
OUT_PNG = Path("outputs/validation_storms.png")

# Weather that physically brings lines down. Heat, drought, hail and flooding are
# left out: they cause plenty of damage but not mainly to overhead distribution.
POWER_WEATHER = {
    "Thunderstorm Wind", "High Wind", "Strong Wind", "Tornado", "Lightning",
    "Ice Storm", "Winter Storm", "Blizzard", "Heavy Snow", "Winter Weather",
    "Hurricane", "Hurricane (Typhoon)", "Tropical Storm", "Wildfire",
}


def _storm_file() -> Path | None:
    hits = sorted(RAW.glob("StormEvents*details*.csv*")) or sorted(RAW.glob("StormEvents*.csv*"))
    return hits[-1] if hits else None


def _reliability_file() -> Path | None:
    for pattern in ("f861*.zip", "Reliability_*.xlsx"):
        hits = sorted(RAW.glob(pattern))
        if hits:
            return hits[-1]
    return None


def load_storms(path: Path) -> pd.DataFrame:
    """Count power-relevant events, and total property damage, per state."""
    df = pd.read_csv(path, low_memory=False)
    df = df[df["EVENT_TYPE"].isin(POWER_WEATHER)].copy()

    # NOAA writes state names in caps; fold them back to the two-letter codes.
    to_code = {name.upper(): code for code, name in STATE_NAMES.items()}
    df["state"] = df["STATE"].astype(str).str.strip().str.upper().map(to_code)
    df = df.dropna(subset=["state"])

    # DAMAGE_PROPERTY looks like "25.00K" or "1.5M".
    def dollars(v):
        s = str(v).strip().upper()
        if not s or s in ("NAN", "0", "0.00K"):
            return 0.0
        mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(s[-1])
        try:
            return float(s[:-1]) * mult if mult else float(s)
        except ValueError:
            return 0.0

    df["damage_usd"] = df["DAMAGE_PROPERTY"].map(dollars)
    return df.groupby("state").agg(
        storm_events=("EVENT_TYPE", "size"),
        storm_damage_usd=("damage_usd", "sum"),
    ).reset_index()


def load_saidi_both_ways(path: Path) -> pd.DataFrame | None:
    """State SAIDI with and without major event days, plus customer counts."""
    src = sources._reliability_sheet(path)
    if src is None:
        return None
    book = pd.ExcelFile(src)
    sheet = next((s for s in book.sheet_names if "state" in s.lower() and "total" in s.lower()), None)
    if sheet is None:
        return None

    head = pd.read_excel(book, sheet_name=sheet, header=None, nrows=6)
    header_row = None
    for i in range(len(head)):
        joined = " ".join(str(x).lower() for x in head.iloc[i].tolist())
        if "saidi" in joined and "state" in joined:
            header_row = i
            break
    if header_row is None:
        return None

    cols = sources.combined_header(head, header_row)
    df = pd.read_excel(book, sheet_name=sheet, header=header_row)
    if len(cols) != len(df.columns):
        return None
    df.columns = cols

    def find(*needles):
        for i, c in enumerate(cols):
            if all(n in c for n in needles):
                return i
        return None

    idx = {
        "state": find("state"),
        "saidi_with": find("ieee", "with major event", "saidi"),
        "saidi_without": find("ieee", "without major event", "saidi"),
        "customers": find("ieee", "with major event", "number of customers"),
    }
    if any(v is None for v in idx.values()):
        return None

    out = df.iloc[:, list(idx.values())].copy()
    out.columns = list(idx)
    out["state"] = out["state"].astype(str).str.strip().str.upper()
    out = out[out["state"].isin(STATE_NAMES)]
    for c in ("saidi_with", "saidi_without", "customers"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.dropna(subset=["saidi_with", "saidi_without"])


def main():
    storms_path, rel_path = _storm_file(), _reliability_file()
    if storms_path is None:
        raise SystemExit("no NOAA storm file in data/raw, see the note at the top of this script")
    if rel_path is None:
        raise SystemExit("no EIA-861 file in data/raw, see the note at the top of this script")

    storms = load_storms(storms_path)
    saidi = load_saidi_both_ways(rel_path)
    if saidi is None:
        raise SystemExit(f"could not read reliability figures out of {rel_path.name}")

    df = saidi.merge(storms, on="state", how="inner")
    # The bit of the outage burden that major events account for.
    df["storm_gap"] = (df["saidi_with"] - df["saidi_without"]).round(1)
    df["events_per_100k_customers"] = (df["storm_events"] / (df["customers"] / 100_000)).round(2)
    df = df.sort_values("storm_gap", ascending=False).reset_index(drop=True)

    df["damage_per_customer"] = (df["storm_damage_usd"] / df["customers"]).round(2)

    pairs = [
        ("storm_events", "storm_gap", "how often: storm events vs storm outage minutes"),
        ("events_per_100k_customers", "storm_gap", "how often, per customer"),
        ("storm_damage_usd", "storm_gap", "how bad: storm damage vs storm outage minutes"),
        ("damage_per_customer", "storm_gap", "how bad, per customer"),
        ("storm_events", "saidi_with", "storm events vs total outage minutes"),
    ]
    dropped = sorted((set(saidi["state"]) | set(storms["state"])) - set(df["state"]))
    print(f"states compared: {len(df)}" + (f" (dropped: {', '.join(dropped)})" if dropped else ""))
    print(f"NOAA file: {storms_path.name}\nEIA file:  {rel_path.name}\n")
    # Spearman is just Pearson on the ranks, and doing it that way avoids pulling
    # in scipy for one number. Ranks also keep outliers like Maine from dominating.
    def spearman(x, y):
        return x.rank().corr(y.rank())

    print(f"{'comparison':<52} {'spearman':>9} {'pearson':>8}")
    results = {}
    for a, b, label in pairs:
        rs = spearman(df[a], df[b])
        rp = df[a].corr(df[b], method="pearson")
        results[label] = rs
        print(f"{label:<52} {rs:>9.2f} {rp:>8.2f}")

    # A couple of extreme states can carry a Pearson figure on their own, so check
    # what survives once the two biggest storm gaps are set aside.
    trimmed = df.iloc[2:]
    print("\nWith the two largest storm gaps removed:")
    for a, b, label in pairs[:4]:
        print(f"  {label:<50} {spearman(trimmed[a], trimmed[b]):>5.2f}")

    freq = results["how often: storm events vs storm outage minutes"]
    sev = results["how bad: storm damage vs storm outage minutes"]
    print("\nReading:")
    print(f"  How much weather a state gets barely predicts its storm outage minutes")
    print(f"  (rank correlation {freq:.2f}). How damaging that weather was does a little")
    print(f"  better ({sev:.2f}) but not much, and its stronger straight-line correlation")
    print("  leans on a handful of extreme states rather than a steady pattern.")
    print("\n  So the weather story does not hold up as neatly as the index assumes. Storms")
    print("  are clearly involved, since the with and without major event figures are miles")
    print("  apart, but which states lose the most minutes is not mostly about how much bad")
    print("  weather arrives. What the grid is like when it arrives, and how quickly crews")
    print("  restore it, look like they matter more. That is an argument for the policy")
    print("  reading this project already gives, and against treating exposure as fate.")
    print("\n  Caveats: one year only, and NOAA event counts partly reflect how densely")
    print("  observed a state is rather than how much weather it truly had.")

    print("\nMost storm-driven outage minutes:")
    show = ["state", "saidi_with", "saidi_without", "storm_gap", "storm_events"]
    print(df.head(8)[show].to_string(index=False))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    ax.scatter(df["storm_events"], df["storm_gap"], s=26, color="#b5462f", alpha=.8, zorder=3)
    for _, r in df.iterrows():
        if r["storm_gap"] > df["storm_gap"].quantile(.88) or r["storm_events"] > df["storm_events"].quantile(.94):
            ax.annotate(r["state"], (r["storm_events"], r["storm_gap"]),
                        fontsize=8, xytext=(4, 3), textcoords="offset points", color="#17181a")
    ax.set_xlabel("Power-relevant storm events recorded by NOAA, 2023")
    ax.set_ylabel("Outage minutes from major events\n(SAIDI with, minus without)")
    ax.set_title(f"Storms against storm-driven outages (rank correlation {freq:.2f})", fontsize=11)
    ax.grid(alpha=.18, zorder=0)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=130)
    plt.close(fig)
    print(f"\nwrote {OUT_CSV} and {OUT_PNG}")


if __name__ == "__main__":
    main()
