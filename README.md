# Grid resilience exposure index

Scores US states by how exposed their electricity systems look, using public
data only. It's a research sketch, not an operational tool — everything is at
the state level and comes from the same EIA data anyone can download. The
coarse granularity is on purpose; this isn't meant to point at anything you
could act on.

![Exposure index by state](outputs/exposure_map_r.png)

The committed run uses the synthetic fallback (no API key was set when I
generated it), so read the ranking as illustrative rather than a finding.

## The idea

Three signals, each pulled from public numbers and oriented so a higher value
means more exposed:

| Component | Built from | Source |
|---|---|---|
| Outage burden | SAIDI / SAIFI reliability metrics | EIA-861 |
| Concentration | Fuel-mix HHI + single-largest-plant share | EIA-860 |
| Exposure deficit | Capacity-to-peak-demand margin + fuel diversity | EIA-860 / 861 |

Each one is normalized (z-score by default), then the three get weighted into a
single 0–100 score and ranked. The weights live in `config.yaml`. I put the
most weight on outage burden because realized reliability is the most direct
evidence — the other two are structural proxies. They're a judgement call, which
is exactly why they sit in one file you can change and re-run.

Worth noting the normalization choice actually moves the ranking: AZ and GA
swap the top spot between z-score and min-max. Not a bug, just a reminder that
the method is sensitive to a couple of defensible decisions.

## Data, and the fallback

Capacity comes from the EIA open API (v2). It needs a free key:

```bash
export EIA_API_KEY=your_key_here      # Windows: setx EIA_API_KEY your_key
```

No key, or a request that falls over, and the pipeline drops to a deterministic
synthetic sample so the run still finishes end to end. Synthetic rows are tagged
in a `source` column and the script says so when it's done — there's no mistaking
one for the other.

The EIA-861 reliability numbers don't have a clean v2 endpoint (they ship as
bulk workbooks), so those use the synthetic path for now. There's a comment in
`grid/sources.py` marking where a real parser would slot in.

## Running it

Python side:

```bash
pip install -r requirements.txt
python pipeline.py
python pipeline.py --normalize minmax --top-n 10   # the knobs
```

What lands:

- `data/interim/state_table.csv` — the cleaned, joined table
- `outputs/exposure_index.csv` — scores plus the per-component breakdown
- `outputs/ranked_states.png` — top-N bar chart
- `outputs/exposure_map.png` — geopandas choropleth (only if geopandas is installed)

![Top exposed states](outputs/ranked_states.png)

### The map and GIS

There are two ways to draw it. The Python pipeline makes a geopandas choropleth
when geopandas is available. I also kept the map I actually use in writeups in
R — `analysis/exposure_map.R`, using sf and ggplot. It reads
`outputs/exposure_index.csv`, joins to lower-48 state polygons, and writes both
a PNG and a GeoPackage:

```bash
Rscript analysis/exposure_map.R
```

Needs R with `sf`, `dplyr`, `ggplot2`, `maps`. Output:

- `outputs/exposure_map_r.png` — the ggplot version (shown above)
- `outputs/exposure_states.gpkg` — scores joined to geometry, openable in QGIS
  or ArcGIS if you want to take the spatial side further

The R map is lower-48 only; Alaska, Hawaii, and DC fall outside the `maps`
polygon set, same as the CONUS crop on the Python side.

## Layout

```
grid/
  sources.py    ingestion + synthetic fallbacks
  cleaning.py   plant rollups, joins, the state table
  scoring.py    components, normalization, composite
  plots.py      bar chart + optional geopandas map
pipeline.py     runs the four steps
analysis/
  exposure_map.R   sf/ggplot map + GeoPackage export
config.yaml     weights, source settings, output options
```

## Caveats

State-level aggregation hides a lot — a state that scores fine can still have
fragile pockets inside it.

HHI and top-plant share are blunt instruments. They say nothing about
transmission topology, which probably matters as much as generation mix, but
that data isn't as cleanly public.

Moving to another region means new source loaders and a different key column.
The cleaning and scoring don't otherwise assume the US — they work off a generic
`state` field — but I haven't actually tried it on non-US data.

## Sources

- EIA Open Data, Forms 860 and 861 — https://www.eia.gov/opendata/
- State polygons: R `maps` package; Natural Earth admin-1 for the Python map
