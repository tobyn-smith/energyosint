# Methodology

Notes on how the exposure index is put together, what the numbers mean, and
where the weak spots are. This is a research sketch, so the point is to be clear
about the choices rather than to claim the result is definitive.

## The question

Which US states look most exposed, in the sense of being more likely to struggle
to keep electricity flowing? Everything is at the state level and comes from
public data, so it is a broad lens, not a precise or operational measure.

## Data

Three inputs, each keyed on the state:

- **Generation capacity** by plant and fuel, from EPA's eGRID workbook, or from
  EIA Form 860 over the open API if a key is set. Used for the concentration
  measures and the capacity margin.
- **Reliability**, the SAIDI and SAIFI outage metrics, from EIA Form 861.
- **Peak demand and net generation**, used for the capacity margin.

When there is no EIA API key, or a request fails, the pipeline falls back to a
seeded synthetic sample so it still runs end to end. Sample rows are tagged in a
`source` column, and each input falls back on its own, so a run can mix real and
sample data. The pipeline prints which it used for each.

The committed results use the real EIA-861 reliability figures for 2023 and real
plant capacity from EPA's eGRID2023, leaving peak demand as the only sample input.
Two of the three components are therefore built on real data, and the third, the
exposure deficit, is part real: the installed capacity side of the margin is real
and only the peak demand it is divided by is not.

EIA-861 reliability, eGRID capacity and state peak demand all ship as bulk
spreadsheets rather than a clean API route. The pipeline will read a local copy of
any of them if you point `config.yaml` at it, and otherwise falls back to the
synthetic path for that input alone.

The reliability workbook takes some care to read. It carries two stacked header
rows, repeats the same column names under "IEEE Standard" and again under "Any
Standard", and writes missing values as ".". I take the IEEE series because it is
the like-for-like one across utilities, including major event days because storms
are the point, and I use the sheet EIA has already aggregated to states. Rolling
the per-utility sheet up by hand would weight a co-op with a few thousand customers
the same as a utility serving millions.

State outlines for the maps come from the R `usmap` package and from Natural
Earth (for the Python version).

## The three components

Each component is built so that a higher value means more exposed.

**Outage burden.** How much interruption customers actually see. SAIDI (minutes
without power per year) does most of the work, with SAIFI (number of
interruptions) as a lighter second signal. I combine them as 0.7 SAIDI and 0.3
SAIFI after putting each on a common scale. This is the most direct evidence of
resilience, since it measures what actually happened rather than how the system
is built.

**Concentration.** How much the supply leans on a single thing. Two parts: a
Herfindahl index of capacity across fuel types (the same concentration score
economists use for market share, from 0 to 10000, higher when one fuel dominates),
and the share of total capacity sitting in the single largest plant.
I weight these 0.6 and 0.4. The idea is that a grid riding on one fuel or one big
asset has more to lose if that thing goes down.

**Exposure deficit.** Whether there is slack and variety in the system. Two
parts: the capacity margin (installed capacity divided by peak demand, where a
tight margin is worse), and fuel diversity (the count of fuel types, where fewer
is worse). Both are flipped so that less slack and less variety score higher, and
combined 0.65 and 0.35.

## Putting them together

Each component is put on a common scale before the three are combined (a z-score
by default, which just measures how far each state sits above or below the
average, with a min-max option as well), so no part dominates only because its
raw numbers happen to be larger. The composite uses the weights in `config.yaml`:

- outage burden 0.45
- concentration 0.30
- exposure deficit 0.25

I put the most weight on outage burden because how often the power really fails
is the most direct signal. The other two are more about how the system is built,
so they count for less. The
weights are normalised to sum to one, and the final composite is rescaled to a 0
to 100 score for readability.

The weights are a judgement call, which is the main reason they live in one file
where they are easy to change.

## How sensitive the ranking is

Because the weights are subjective, `analysis/weight_sensitivity.py` re-scores
the states under a few different weightings and checks how steady the top of the
table is. Six states (AR, KY, LA, MS, OK, WV) stay in the top 10 under every
weighting, while others move a lot. Tennessee, for example, runs from 10th under an
outage-heavy weighting to 42nd under a structure-heavy one. So the very top is
fairly stable, but the middle of the table should be read with that movement in
mind.

The choice of normalisation matters little at the top: z-score and min-max both
give West Virginia, Mississippi and Maine as the first three. It
still moves the middle around, and it changes which component is named as a
state's driver quite a lot, which is worth knowing before quoting that label.

## Limitations

- State-level aggregation hides a lot. A state can look fine overall and still
  have fragile pockets inside it.
- The concentration measures are blunt. They say nothing about the transmission
  network that moves power around, which probably matters at least as much, but
  that data is harder to get cleanly.
- Peak demand is still a sample figure, so the capacity margin inside the
  exposure deficit is illustrative. Outage burden and concentration are both built
  entirely on real data.
- The live EIA-860 API path is written but not heavily tested, since it needs a
  key. In practice eGRID covers the same ground without one. The reliability loader is tested against a fixture shaped like the real
  workbook, and has been run against the real 2023 file.
- Checked against NOAA storm records, the outage data does not line up with
  severe weather as neatly as the framing here assumes. See the validation section
  in the README. I have left the framing as it is and reported the mismatch rather
  than quietly adjusting one to fit the other.
- The code is written against a generic state column rather than hard-coding the
  US, so in principle it could move to another region, but that has not been
  tried.

## What this is not

This is not an operational tool and not a way to point at specific vulnerable
infrastructure. It works from aggregate, public, state-level figures, the same
kind of data used in energy reporting and academic work, and the coarse
granularity is intentional.

## Reproducing

`python pipeline.py` runs ingestion, cleaning, scoring, and the charts. The
README has the full setup, including the optional R map and how to supply a live
EIA key.
