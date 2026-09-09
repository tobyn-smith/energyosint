"""Check the published figures still hold together.

The results table and the site JSON are committed to the repo and only refreshed
by hand, from agency workbooks too large to keep here. That leaves a few ways for
them to go quietly wrong between refreshes, so this looks for each one.

First the obvious corruption: a score outside 0 to 100, a missing value, a state
code that is not one of the 51, a rank that has gone astray.

Then the two files drifting apart. outputs/exposure_index.csv, which the README
and the API describe, and docs/data/index.json, which the web deck reads, are
written from the same run, so they have to agree; if one is regenerated and the
other is not, the table and the map start telling different stories.

Then the useful one: figures that were typed in rather than computed. Every
published score, rank and driver has to fall back out of the three components when
the weights are re-applied, using the same maths the pipeline uses. A hand-edited
or made-up number will not reproduce, so recomputing and comparing is a cheap way
to tell real output from a good guess.

None of this needs the real data or a key, so it runs anywhere against whatever is
committed, and exits non-zero with the reason on any failure.

    python analysis/validate_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from grid.regions import STATE_NAMES

CSV = ROOT / "outputs" / "exposure_index.csv"
SITE = ROOT / "docs" / "data" / "index.json"
CONFIG = ROOT / "config.yaml"

COMPONENTS = ["outage_burden", "infra_concentration", "exposure_deficit"]
# JSON keys the deck uses, in the same order as COMPONENTS.
SITE_KEYS = {"outage_burden": "o", "infra_concentration": "c", "exposure_deficit": "d"}

# The site is rounded to 4 dp, so allow a little slack when matching it to the
# full-precision CSV; the score recompute only has to survive rounding to 1 dp.
COMPONENT_TOL = 1e-2
SCORE_TOL = 0.2


class DataError(Exception):
    """A specific reason the published figures cannot be trusted."""


def _weights(cfg: dict) -> dict:
    w = cfg["weights"]
    total = sum(w[c] for c in COMPONENTS)
    if total <= 0:
        raise DataError("config weights sum to zero, cannot recompute scores")
    return {c: w[c] / total for c in COMPONENTS}


def _load() -> tuple[pd.DataFrame, list[dict], dict]:
    for path in (CSV, SITE, CONFIG):
        if not path.exists():
            raise DataError(f"missing {path.relative_to(ROOT)}")
    csv = pd.read_csv(CSV)
    site = json.loads(SITE.read_text(encoding="utf-8"))
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return csv, site, cfg


def _check_structure(csv: pd.DataFrame) -> None:
    needed = {"rank", "state", "exposure_score", "driver", *COMPONENTS}
    missing = needed - set(csv.columns)
    if missing:
        raise DataError(f"{CSV.name} is missing columns: {', '.join(sorted(missing))}")

    if csv[list(needed)].isna().any().any():
        bad = [c for c in needed if csv[c].isna().any()]
        raise DataError(f"{CSV.name} has NaNs in: {', '.join(sorted(bad))}")

    unknown = sorted(set(csv["state"]) - set(STATE_NAMES))
    if unknown:
        raise DataError(f"{CSV.name} has state codes not in the 50 states + DC: {', '.join(unknown)}")
    if csv["state"].duplicated().any():
        dupes = sorted(csv.loc[csv["state"].duplicated(), "state"])
        raise DataError(f"{CSV.name} repeats states: {', '.join(dupes)}")
    if len(csv) != len(STATE_NAMES):
        raise DataError(
            f"{CSV.name} covers {len(csv)} states, expected all {len(STATE_NAMES)} "
            "(50 states + DC); the map on the site needs every one"
        )

    lo, hi = csv["exposure_score"].min(), csv["exposure_score"].max()
    if lo < 0 or hi > 100:
        raise DataError(f"exposure_score out of the 0-100 range (min {lo}, max {hi})")
    # The rescale pins the extremes, so a real run always touches both ends.
    if not (abs(lo) < SCORE_TOL and abs(hi - 100) < SCORE_TOL):
        raise DataError(f"exposure_score should span 0 to 100 but runs {lo} to {hi}")

    ranks = sorted(csv["rank"].tolist())
    if ranks != list(range(1, len(csv) + 1)):
        raise DataError(f"{CSV.name} ranks are not 1..{len(csv)} without gaps or repeats")


def _check_files_agree(csv: pd.DataFrame, site: list[dict]) -> None:
    site_states = [row["s"] for row in site]
    if len(site_states) != len(set(site_states)):
        raise DataError(f"{SITE.name} repeats states")
    if set(site_states) != set(csv["state"]):
        only_csv = sorted(set(csv["state"]) - set(site_states))
        only_site = sorted(set(site_states) - set(csv["state"]))
        raise DataError(
            f"{CSV.name} and {SITE.name} cover different states "
            f"(only in csv: {only_csv or '-'}; only in site: {only_site or '-'})"
        )

    by_state = csv.set_index("state")
    for row in site:
        st = row["s"]
        if row.get("n") != STATE_NAMES.get(st):
            raise DataError(f"{SITE.name} names {st} as {row.get('n')!r}, expected {STATE_NAMES.get(st)!r}")
        for comp, key in SITE_KEYS.items():
            csv_val = float(by_state.loc[st, comp])
            site_val = float(row[key])
            if abs(csv_val - site_val) > COMPONENT_TOL:
                raise DataError(
                    f"{st}: {comp} disagrees between files "
                    f"({CSV.name}={csv_val:.4f}, {SITE.name}={site_val:.4f}); "
                    "one of the two was regenerated without the other"
                )


def _check_scores_are_real(csv: pd.DataFrame, weights: dict) -> None:
    """Recompute each score and rank from the components and check it matches what
    was published. A made-up number will not reproduce."""
    comp = csv.set_index("state")[COMPONENTS]

    # driver = the component a state stands highest on (matches scoring.py).
    recomputed_driver = comp.idxmax(axis=1)
    mismatched = csv.set_index("state")["driver"][recomputed_driver.index] != recomputed_driver
    if mismatched.any():
        bad = ", ".join(mismatched[mismatched].index[:5])
        raise DataError(f"driver label does not match the top component for: {bad}")

    blend = sum(comp[c] * weights[c] for c in COMPONENTS)
    lo, hi = blend.min(), blend.max()
    if hi <= lo:
        raise DataError("all states blend to the same value, the score would be degenerate")
    recomputed_score = ((blend - lo) / (hi - lo) * 100).round(1)

    published = csv.set_index("state")["exposure_score"]
    gap = (recomputed_score - published).abs()
    worst = gap.idxmax()
    if gap.max() > SCORE_TOL:
        raise DataError(
            f"published exposure_score is not reproducible from the components: "
            f"{worst} says {published[worst]} but the weights give {recomputed_score[worst]:.1f} "
            "(the figures look edited rather than computed)"
        )

    recomputed_rank = blend.rank(ascending=False, method="min").astype(int)
    rank_gap = (recomputed_rank - csv.set_index("state")["rank"]).abs()
    if rank_gap.max() > 0:
        off = rank_gap.idxmax()
        raise DataError(
            f"published rank is not reproducible from the components: {off} is ranked "
            f"{int(csv.set_index('state').loc[off, 'rank'])} but recomputes to {int(recomputed_rank[off])}"
        )


def validate() -> None:
    csv, site, cfg = _load()
    weights = _weights(cfg)
    _check_structure(csv)
    _check_files_agree(csv, site)
    _check_scores_are_real(csv, weights)


def main() -> int:
    try:
        validate()
    except DataError as err:
        print(f"data check FAILED: {err}")
        return 1
    print(f"data check passed: {len(STATE_NAMES)} states, "
          f"{CSV.relative_to(ROOT)} and {SITE.relative_to(ROOT)} agree and reproduce.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
