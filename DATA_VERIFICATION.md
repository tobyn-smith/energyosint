# Data verification note

Checked on 27 October 2026 against public EIA files and the EIA Open Data API.
This note records what was actually compared. It does not re-score the index
or change any committed results.

## EIA-861 reliability (2023)

**Claim in the repo.** The committed outage minutes in
`outputs/exposure_index.csv` are EIA-861, 2023, IEEE standard, including major
event days, from the State Totals sheet.

**Source.** Official zip linked from
[Form EIA-861 detailed data files](https://www.eia.gov/electricity/data/eia861/):
`https://www.eia.gov/electricity/data/eia861/archive/zip/f8612023.zip`
(HTTP 200, `Reliability_2023.xlsx` inside). The current year's zip is now 2025;
2023 has moved to the archive path.

**How.** Downloaded that zip. Read sheet `State Totals` independently (header
row 3, column 2 = state, column 4 = IEEE SAIDI with major event days). Also ran
the project's loader (`grid.sources._live_reliability`) against the same zip.
Compared both to `saidi_minutes` in `outputs/exposure_index.csv` for all 51
places (50 states and DC).

**Result.** All 51 SAIDI values match to one decimal place (maximum absolute
difference 0.0). Examples:

| State | Committed SAIDI (minutes) | EIA-861 State Totals |
|---|---:|---:|
| ME | 1863.0 | 1863.0 |
| GA | 342.7 | 342.7 |
| WV | 751.5 | 751.5 |
| HI | 248.8 | 248.8 |
| DC | 71.9 | 71.9 |

Issue #2 asked for a real EIA-861 parser. That loader is already in
`grid/sources.py`. This check confirms the committed outage minutes are the
figures from the public 2023 workbook, not the synthetic sample.

**Not compared to committed files.** SAIFI is used inside the outage-burden
component but is not a column on `outputs/exposure_index.csv`, so it was not
matched row-for-row against published output. The same IEEE-with-major-event
columns in the workbook give GA 1.858, ME 3.314, HI 3.922.

## EIA Open Data: operating generator capacity (issue #3)

**Claim in the repo.** `_live_plants` talks to
`/v2/electricity/operating-generator-capacity/data/` and maps fields
`stateid`, `plantName`, `energy_source_desc`, `nameplate-capacity-mw`.

**Source.** EIA API metadata and a 2-row sample, using EIA's public demo key:

- `GET https://api.eia.gov/v2/electricity/operating-generator-capacity/?api_key=DEMO_KEY`
- `GET .../data/?api_key=DEMO_KEY&frequency=monthly&data[0]=nameplate-capacity-mw&length=2`

**Result.** Route and series id are real. Sample records (period `2026-08`)
include:

| Code uses | API actually returns | Match? |
|---|---|---|
| `stateid` | `stateid` | yes |
| `plantName` | `plantName` | yes |
| `nameplate-capacity-mw` | `nameplate-capacity-mw` (listed under `data`) | yes |
| `energy_source_desc` | `energy-source-desc` (hyphens, not underscores) | no |

The guessed fuel field would therefore be missing, and a keyed run would fall
back to eGRID or the sample. The mapping now accepts both names so a live pull
can find the fuel column. That does not change the committed scores: those
capacity figures come from EPA eGRID, not from this API.

**Still not a full live-path check.** No complete national pull was run (the
dataset is millions of monthly rows and needs pagination). Fuel *labels* from
the API are long descriptions such as "Disillate Fuel Oil", not the short names
the rest of the pipeline uses (`natural_gas`, `oil`, and so on), so a keyed
EIA-860 run would still need a fuller fuel map before it should replace eGRID.
`energy_source_code` (for example `DFO`, `NG`) is the stable facet; it was not
wired into scoring.

## Georgia page (EIA State Electricity Profile 2024)

**Source.** [Georgia Electricity Profile 2024](https://www.eia.gov/electricity/state/georgia/),
Table 1, data year 2024.

**Result.** The rounded figures on `docs/georgia.html` match that table:

| Page | EIA Table 1 |
|---|---|
| 140 TWh net generation, 8th | 139,805,428 MWh (8th) |
| 39,746 MW summer capacity, 7th | 39,746 (7th) |
| Natural gas as largest source | Primary energy source: Natural gas |
| 11.4 cents/kWh, 26th | 11.40 (26th) |
| 150 TWh retail sales, 5th | 150,003,965 MWh (5th) |
| 28 GW regulated utilities | Electric utilities net summer capacity 28,096 MW |

Those profile figures are context on the Georgia page. They are not inputs to
the exposure score.

## What was not verified against EIA

- **Plant capacity in the committed index.** Documented as EPA eGRID2023, not
  EIA. No eGRID workbook was downloaded here, and no EIA-860 national inventory
  was compared to `fuel_hhi` or `top_plant_share`.
- **Peak demand.** Still the built-in sample. There is no committed real demand
  file to check.
- **Scores, ranks, and weights.** Internal consistency is already covered by
  `python analysis/validate_data.py` (the CSV and the site JSON agree and the
  scores recompute from the three components). That is not an EIA check.
- **NOAA storm counts.** Out of scope for an EIA check.
- **EIA-861 years other than 2023.** 2024 and 2025 zips exist on the same EIA
  page. They were not compared, because the committed results are labelled 2023.

## Reproduce the SAIDI check

```bash
curl -fsSL -o /tmp/f8612023.zip \
  https://www.eia.gov/electricity/data/eia861/archive/zip/f8612023.zip
# then point config.yaml sources.reliability_workbook at that zip, or run the
# comparison used for this note (open Reliability_2023.xlsx, sheet State Totals,
# IEEE SAIDI with major event days, against outputs/exposure_index.csv)
```
