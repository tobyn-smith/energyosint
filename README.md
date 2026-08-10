<h1 align="center">Grid Resilience Exposure Index</h1>

<p align="center">
  Which US states look most exposed to losing power, and what is driving it.<br>
  Every state gets one score from 0 to 100, built only from public government data.
</p>

<p align="center">
  <a href="https://github.com/tobyn-smith/energyosint/actions/workflows/build.yml"><img alt="build" src="https://github.com/tobyn-smith/energyosint/actions/workflows/build.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="licence: MIT" src="https://img.shields.io/badge/licence-MIT-blue.svg"></a>
</p>

<p align="center">
  <b><a href="https://tobyn-smith.github.io/energyosint/">Open the interactive deck</a></b> ·
  <a href="https://tobyn-smith.github.io/energyosint/georgia.html">Georgia deep dive</a> ·
  <a href="METHODOLOGY.md">Methodology</a>
</p>

![Map of exposure scores by state](outputs/exposure_map.png)

I am an international affairs student who codes, so this sits between the two:
the analysis is a proper pipeline, and the write-up is aimed at someone who has
to think about energy policy rather than wiring. It works at the state level, so
it is a broad lens rather than anything operational.

> **On the numbers.** Outage figures are real (EIA-861, 2023) and plant capacity
> is real (EPA eGRID2023). Only peak demand still comes from a built-in sample.
> The pipeline prints which inputs were real on every run.

**Contents** ·
[What it found](#what-it-found) ·
[Under the hood](#what-is-under-the-hood) ·
[How the score works](#how-the-score-works) ·
[Quick start](#quick-start) ·
[Data](#data-and-the-sample-fallback) ·
[Validation](#does-the-outage-data-hold-up) ·
[API](#a-json-api) ·
[Layout](#how-the-project-is-laid-out)

## What it found

Four things stand out. The second is the one I would actually carry into a
policy conversation, and the last is the one I did not expect.

- **The top of the table is stable.** Six states (AR, KY, LA, MS, OK, WV) stay in
  the top 10 under every weighting I tried, and West Virginia and Mississippi come
  first and second whichever way the scaling is done. The middle moves a lot, so it
  should be read loosely.
- **The same score means different things in different places.** Mississippi and
  West Virginia have the two most fuel-concentrated supplies in the country, one
  leaning on gas and the other on coal, and they take the top two places on that
  alone. Maine is third for the opposite reason: it has the least concentrated fuel
  mix of any state and still lost its customers thirty one hours of power in 2023.
  That changes the policy lever, because spreading a fuel mix is not the same job as
  hardening lines.
- **Two of the three parts overlap, though less than they used to.** Concentration
  and the exposure deficit correlate at about 0.33, so the structural side is still
  counted a little twice. On the earlier synthetic capacity data that figure was
  0.5, so real plant data pulled the two measures further apart.
- **The weather story does not hold up as neatly as expected.** Checked against
  NOAA's storm records, how much damaging weather a state gets barely predicts how
  many outage minutes it loses to storms (rank correlation 0.21). Texas and Georgia
  log the most storm events in the country and lose few minutes; Maine logs a
  fraction as many and lost the most. [More below](#does-the-outage-data-hold-up).
  This one is unaffected by the capacity data, since both sides come from elsewhere.

The top ten as it currently stands, straight from `outputs/exposure_index.csv`:

| # | State | Score | Mostly driven by | Outage minutes, 2023 |
|---:|---|---:|---|---:|
| 1 | West Virginia | 100.0 | concentration | 752 |
| 2 | Mississippi | 99.4 | concentration | 878 |
| 3 | Maine | 93.0 | outages | 1,863 |
| 4 | Oklahoma | 76.6 | outages | 1,339 |
| 5 | Arkansas | 72.6 | thin spare capacity | 915 |
| 6 | Kentucky | 67.1 | outages | 862 |
| 7 | Rhode Island | 64.5 | concentration | 105 |
| 8 | Louisiana | 62.1 | outages | 663 |
| 9 | Hawaii | 60.2 | concentration | 249 |
| 10 | Michigan | 53.9 | outages | 1,128 |

## What is under the hood

| | |
|---|---|
| **Pipeline** | Python (pandas, numpy) that ingests, cleans, scores and plots, with a seeded sample so it runs for anyone with no API key |
| **Testing** | 29 tests covering the scoring maths, the spreadsheet loaders and the API, run by a GitHub Action on every change to the analysis code |
| **Mapping** | Done in both languages: a Python choropleth via geopandas and an R map via `usmap`, plus a GeoPackage export that opens in QGIS |
| **Storage** | A SQLite store of every run, and an optional FastAPI service that re-ranks the states live for any weights, using the same scoring code as the pipeline |
| **Front end** | No JavaScript libraries: the deck, the two interactive maps and the weight explorer are hand-written SVG and vanilla JS |

## How the score works

Every state gets one number, an "exposure score" from 0 to 100. A higher score
means the state looks more exposed, meaning more likely to have trouble keeping
the power on. The darker a state is on the map, the higher its score.

That single number is built from three simpler ideas, all taken from public
figures:

1. **Outage burden.** How often the power actually goes out, and for how long.
   The electricity industry tracks this with two standard measures called SAIDI
   and SAIFI. More and longer outages count as worse.

2. **Concentration.** How much of a state's power leans on one type of fuel, or
   on a single very large plant. If a lot depends on one thing, losing that one
   thing hurts more.

3. **Exposure deficit.** Whether a state has much spare generating capacity
   above its busiest demand, and whether its power supply is varied. Tight
   margins and little variety count as worse.

Each piece is put onto the same scale and then blended into the final score.
How much each piece counts is set in the `config.yaml` file, so you can change
the weights and run it again. I put the most weight on outage burden, because
how often the power really fails is the most direct evidence. The other two are
more about the underlying setup.

The scaling method barely shifts the top of the table: z-score and min-max both
put West Virginia, Mississippi and Maine in the first three. Further down it matters more,
so the exact position of a middling state depends on choices made in the settings.

The [project page](https://tobyn-smith.github.io/energyosint/) is an interactive
slide deck. If you would rather not click through it, the "read view" button in
the corner lays the same slides out as one continuous page, and printing does the
same thing. You can click through it with the arrow keys, the marks along the
bottom, or a swipe on your phone. The three weights are sliders on it, and moving
them re-ranks the table and re-shades the map live; you can also hover any state
to see its score and what is driving it. There is a separate, deeper dive on
Georgia too. It sets the score next to the state's real figures from the EIA, EPA
and NOAA, and has a map of every large power plant that you can filter by fuel.

Nothing in the scoring is US-specific, by the way. Given the same three inputs it
would run on any country's regions or provinces. It is written against the US
because the EIA publishes enough open data to build the whole thing from, which
few statistical agencies anywhere do.

## Quick start

With Python installed, from the project folder:

```bash
pip install -r requirements.txt
python pipeline.py
```

That is the whole thing. It prints its progress, shows the most exposed states,
and writes its results into the `outputs` folder.

Two settings can be changed without editing any files. `--normalize` switches the
scaling method and `--top-n` sets how many states show up in the bar chart:

```bash
python pipeline.py --normalize minmax --top-n 10
```

<details>
<summary><b>Never installed Python before?</b></summary>

<br>

You do not have to be a programmer to run this, but you do need one free tool.

1. Go to https://www.python.org/downloads and install Python 3.
2. On Windows, during the installer, tick the box that says
   "Add Python to PATH". This matters.
3. To check it worked, open a terminal (Command Prompt or PowerShell on
   Windows, Terminal on Mac) and type `python --version`. You should see a
   version number.

The steps above assume you have opened a terminal and moved into the project
folder. If you are not sure how to move into the folder, the usual command is
`cd` followed by the path, for example `cd Downloads/energyosint`.

</details>

<details>
<summary><b>Drawing the map in R (optional)</b></summary>

<br>

The R map is optional; the Python one is what the README shows. If you want it,
install R from https://cran.r-project.org, then run this once to get the
packages:

```bash
Rscript -e "install.packages(c('usmap','ggplot2'))"
```

Then draw the map:

```bash
Rscript analysis/exposure_map.R
```

</details>

<details>
<summary><b>The other analysis scripts</b></summary>

<br>

These all read what the pipeline writes, so run `python pipeline.py` first.

```bash
python analysis/weight_sensitivity.py   # how much the weights move the ranking
python analysis/regional_summary.py     # roll the scores up to census regions
python analysis/component_overlap.py    # do the three parts measure the same thing
python analysis/validate_outages.py     # check the outage data against NOAA storms
python analysis/report.py               # write a short findings summary
```

</details>

### What you get

After running, look in the `outputs` folder:

| File | What it is |
|---|---|
| `exposure_index.csv` | The main result. Every state, its score, its rank, and the three pieces behind it. Opens in Excel or Google Sheets. |
| `ranked_states.png` | A bar chart of the most exposed states. |
| `exposure_map.png` | The map drawn by Python (the one at the top of this page). |
| `exposure_map_r.png` | The same map drawn by R, if you have run the R script. |
| `exposure_states.gpkg` | The map data as a GeoPackage, so it opens in QGIS as a real map layer. |
| `index.db` | A SQLite record of every run, which the API reads. |

The Python map and the GeoPackage need an extra library called geopandas. If you
want them, run `pip install geopandas` first. Without it the pipeline still runs
and just skips those two files (it prints a line saying so). The bar chart and
the results table do not need it.

There is also a `data` folder with the cleaned table and the raw inputs, in case
you want to see the numbers at each step.

![Bar chart of the most exposed states](outputs/ranked_states.png)

## Data and the sample fallback

The real generation data comes from the EIA open data service. Using it needs a
free key. You request one at https://www.eia.gov/opendata, then save it where
the project can find it:

```bash
setx EIA_API_KEY your_key_here     # Windows
export EIA_API_KEY=your_key_here   # Mac or Linux
```

If there is no key, or the download fails, the project quietly switches to a
built-in sample so it still runs from start to finish. Sample rows are marked in
a `source` column, and the program says so when it finishes, so you can always
tell which one you got. If you would rather the run stop than fall back to sample
data, set `allow_synthetic_fallback: false` in `config.yaml`.

Two of the inputs, the outage numbers (SAIDI and SAIFI) and state peak demand, do
not have a clean API endpoint the way the generation data does. EIA ships them as
bulk spreadsheets instead. Download the one you want and point `config.yaml` at it
(`reliability_workbook` and `demand_file`, either an absolute path or a file in
`data/raw`), and the pipeline reads it; if a file is missing it falls back to the
sample for that input alone. So a run can mix real and sample data, and it prints
exactly which it used:

```
[1/4] ingesting public data
      capacity: synthetic
      reliability: eia861
      demand: synthetic
```

The committed results were produced that way. The outage figures are the real
EIA-861 ones for 2023, from `f8612023.zip` on the
[EIA-861 page](https://www.eia.gov/electricity/data/eia861/). That file is not in
the repo, since it is EIA's to distribute and `data/raw` is ignored, so download it
yourself to reproduce the numbers exactly.

Reading it is fiddlier than it sounds, which is why there are tests for it. The
sheet has two stacked header rows, repeats the same column names under "IEEE
Standard" and again under "Any Standard", and writes missing values as ".". The
loader takes the IEEE figures including major event days, and uses the sheet EIA
has already aggregated to states rather than averaging utilities by hand, which
would count a small co-op the same as one serving millions.

## Does the outage data hold up?

The index leans hardest on outage burden, so `analysis/validate_outages.py` checks
it against a source collected by somebody else entirely: NOAA's Storm Events
Database, compiled by the National Weather Service.

The test is a sharp one. EIA publishes outage minutes twice, once counting major
storm days and once excluding them, so the difference is the part storms account
for. If the weather story is right, that gap should track how much damaging
weather a state actually had.

It mostly does not. Across the fifty places that report both figures (all but
Hawaii, which only publishes the one), the rank correlation is 0.21 against the
number of damaging storms and 0.24 against how much damage they did. Texas and
Georgia record the most power-relevant storm events in the country and lose few
minutes to them; Maine records a fraction as many and lost more than anyone.

Storms clearly matter, or the two outage figures would not be so far apart. But
how much bad weather arrives does not decide who suffers most, which points at how
the grid is built and how quickly crews restore it. That is an argument against
treating exposure as fate. It is one year of data and NOAA event counts partly
reflect how densely a state is observed, so I would not lean on it harder than
that, but it is a real result and it is reported as it came out.

![Storms against storm-driven outages](outputs/validation_storms.png)

## Digging further

<details>
<summary><b>How much the weights matter</b></summary>

<br>

The weights are a judgement call, so `analysis/weight_sensitivity.py` re-scores
the states under a few different weightings and prints which ones stay in the top
10. Six states (AR, KY, LA, MS, OK, WV) land in the top 10 no matter how the
weights are set, while others move around a lot. Tennessee, for instance, runs
from 10th under an outage-heavy weighting to 42nd under a structure-heavy one. So
the very top of the table is fairly stable, but the middle depends on the choices,
which is worth keeping in mind when reading it.

The full reasoning behind the components, the weights, and the limitations is
written up in [METHODOLOGY.md](METHODOLOGY.md).

</details>

<details>
<summary><b>A regional view</b></summary>

<br>

`analysis/regional_summary.py` averages the state scores up to the four US Census
regions, which is often an easier way to read the pattern. The South comes out
highest, then the Northeast, and the telling part is that they get there for
different reasons: the South and Midwest through actual outages, the Northeast and
West through how concentrated their supply is. It writes `outputs/regional_summary.csv` and the chart below. Run it
with `--level division` for the finer nine-way census split.

![Average exposure by US Census region](outputs/regional_exposure.png)

</details>

<details>
<summary><b>Do the three parts overlap?</b></summary>

<br>

`analysis/component_overlap.py` checks how much the three components correlate,
since adding them up only makes sense if they are not all measuring the same
thing. Outage burden turns out to be its own signal, but concentration and the
exposure deficit move together (about 0.33): a state with a concentrated supply
also tends to have a tighter, less varied one. So the index leans on that
structural side of things a little twice, which is worth flagging rather than
hiding. That overlap was 0.5 while capacity came from the synthetic sample, so
swapping in real plant data pulled the two apart a fair way.

</details>

## A JSON API

If you want the numbers as an API rather than files, there is a small optional
server. It reads whatever the pipeline last saved to the SQLite database and can
also re-rank the states live for any set of weights, using the same scoring code
the pipeline uses so the two never disagree.

```bash
pip install -r requirements-api.txt
python pipeline.py            # once, so there is a run to serve
uvicorn server:app --reload
```

Then open http://127.0.0.1:8000/docs for the interactive list, or call it directly:

| Endpoint | What it gives you |
|---|---|
| `GET /api/states` | The full scored table, or `/api/states/GA` for one state |
| `GET /api/score?wO=60&wC=20&wD=20&top=10` | Re-ranks live for your own weights |
| `GET /api/regions?level=region` | Rolls the scores up, or `level=division` |
| `GET /api/runs`, `GET /health` | What is stored |

Every pipeline run is also saved to `outputs/index.db` (a SQLite file) and written
out to `docs/data/index.json`, which is what the web deck reads. That file is
refreshed locally rather than in CI: the real figures come from agency workbooks
that are too large to commit and not mine to redistribute, so a runner without them
would fall back to the sample and quietly overwrite the real numbers.

## How the project is laid out

```
grid/            the analysis code, split into small steps
  sources.py     gets the data (real or sample)
  cleaning.py    tidies it up and joins it together
  scoring.py     builds the three pieces and the final score
  plots.py       the bar chart and the Python map
  store.py       saves each run to a small SQLite database
  regions.py     census region lookups and state names, shared around
pipeline.py      runs all the steps in order
server.py        an optional JSON API over the results
analysis/
  exposure_map.R         the R version of the map
  weight_sensitivity.py  checks how much the weights move the ranking
  regional_summary.py    averages the scores up to US Census regions
  component_overlap.py   checks whether the three parts overlap
  report.py              writes a short findings summary
  validate_outages.py    checks the outage data against NOAA storm records
  social_card.py         draws the link preview image for the site
docs/            the interactive slide deck and the Georgia deep dive
  data/index.json  the per-state data the deck reads, refreshed by the pipeline
  assets/og.png    the link preview image
config.yaml      the weights and other settings
requirements-api.txt  extra libraries for the API only
METHODOLOGY.md   the longer write-up of the choices and limits
.github/workflows/build.yml  rebuilds the site data on push
```

## Sources

- EIA Open Data, Forms 860 and 861, https://www.eia.gov/opendata
- EIA-861 reliability, https://www.eia.gov/electricity/data/eia861/
- NOAA Storm Events Database, https://www.ncei.noaa.gov/stormevents/
- EPA eGRID, https://www.epa.gov/egrid (plant capacity, and the Georgia page)
- State map shapes: the R `usmap` package, and Natural Earth boundaries for the
  Python map

## Licence

MIT licence, see [LICENSE](LICENSE). Use it however you like.
