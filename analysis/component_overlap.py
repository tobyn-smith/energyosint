"""Do the three parts of the score actually measure different things?

Adding three components together only makes sense if they are not all saying the
same thing. This checks how much they correlate, both with each other and with
the final score. Run the main pipeline first so outputs/exposure_index.csv
exists.

    python analysis/component_overlap.py
"""

from pathlib import Path

import pandas as pd

INDEX = Path("outputs/exposure_index.csv")
PARTS = ["outage_burden", "infra_concentration", "exposure_deficit"]


def main():
    if not INDEX.exists():
        raise SystemExit("run `python pipeline.py` first, outputs/exposure_index.csv is missing")

    df = pd.read_csv(INDEX)

    corr = df[PARTS].corr().round(2)
    print("How the three parts correlate with each other:")
    print(corr.to_string())

    # Find the closest pair off the diagonal.
    pairs = [(PARTS[i], PARTS[j], corr.iloc[i, j])
             for i in range(len(PARTS)) for j in range(i + 1, len(PARTS))]
    a, b, r = max(pairs, key=lambda p: abs(p[2]))
    print(f"\nClosest pair: {a} and {b} at {r:.2f}.")
    if abs(r) >= 0.4:
        print("Enough overlap that they partly capture the same thing, so the index")
        print("leans on that signal a little twice.")
    else:
        print("Nothing above 0.4, so the three parts are mostly pulling apart.")

    vs_score = df[PARTS + ["exposure_score"]].corr()["exposure_score"][PARTS].round(2)
    print("\nHow much each part tracks the final score:")
    print(vs_score.to_string())

    corr.to_csv("outputs/component_correlations.csv")
    print("\nwrote outputs/component_correlations.csv")


if __name__ == "__main__":
    main()
