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

- **Generation capacity** by plant and fuel, from EIA Form 860 (the open API).
  Used for the concentration measures and the capacity margin.
- **Reliability**, the SAIDI and SAIFI outage metrics, from EIA Form 861.
- **Peak demand and net generation**, used for the capacity margin.

When there is no EIA API key, or a request fails, the pipeline falls back to a
seeded synthetic sample so it still runs end to end. Sample rows are tagged in a
`source` column. The committed results were produced from the sample, so the
ranking shown in the repo is illustrative.

One honest gap: EIA-861 reliability ships as bulk spreadsheets rather than a
clean API route, so the outage component currently uses the synthetic path even
when a key is set. The code marks where a real loader would slot in.

State outlines for the maps come from the R `usmap` package and from Natural
Earth (for the Python version).

## The three components

Each component is built so that a higher value means more exposed.

**Outage burden.** How much interruption customers actually see. SAIDI (minutes
without power per year) does most of the work, with SAIFI (number of
interruptions) as a lighter second signal. I combine them as 0.7 SAIDI and 0.3
SAIFI after standardising each. This is the most direct evidence of resilience,
since it measures realised outcomes rather than structure.

**Concentration.** How much the supply leans on a single thing. Two parts: a
Herfindahl index of capacity across fuel types (0 to 10000, higher when one fuel
dominates), and the share of total capacity sitting in the single largest plant.
I weight these 0.6 and 0.4. The idea is that a grid riding on one fuel or one big
asset has more to lose if that thing goes down.

**Exposure deficit.** Whether there is slack and variety in the system. Two
parts: the capacity margin (installed capacity divided by peak demand, where a
tight margin is worse), and fuel diversity (the count of fuel types, where fewer
is worse). Both are flipped so that less slack and less variety score higher, and
combined 0.65 and 0.35.

## Putting them together

Each component is standardised (z-score by default, with a min-max option), so
the three sit on a common scale before they are combined. The composite uses the
weights in `config.yaml`:

- outage burden 0.45
- concentration 0.30
- exposure deficit 0.25

I put the most weight on outage burden because realised reliability is the most
direct signal. The other two are structural proxies, so they count for less. The
weights are normalised to sum to one, and the final composite is rescaled to a 0
to 100 score for readability.

The weights are a judgement call, which is the main reason they live in one file
where they are easy to change.

## How sensitive the ranking is

Because the weights are subjective, `analysis/weight_sensitivity.py` re-scores
the states under a few different weightings and checks how steady the top of the
table is. On the sample data, six states (AZ, GA, MS, NM, TX, WA) stay in the top
10 under every weighting, while others move a lot. West Virginia, for example,
runs from 4th under an outage-heavy weighting to 23rd under a structure-heavy
one. So the very top is fairly stable, but the middle of the table should be read
with that movement in mind.

The choice of normalisation matters too: Arizona and Georgia swap the top spot
between the z-score and min-max versions.

## Limitations

- State-level aggregation hides a lot. A state can look fine overall and still
  have fragile pockets inside it.
- The concentration measures are blunt. They say nothing about the transmission
  network that moves power around, which probably matters at least as much, but
  that data is harder to get cleanly.
- The outage component uses synthetic data for now, as noted above. Wiring up the
  real EIA-861 files is the obvious next step.
- The live EIA-860 path is written but not heavily tested, since it needs a key.
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
