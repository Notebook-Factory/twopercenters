# Author identity is the bottleneck

Measured 2026-09-14, against `data_parquet/`.

## The ambiguous branch produces no cross-edition linkage at all

| | authors | mean editions each | appear exactly once |
|---|---|---|---|
| unambiguous | 286,105 | 4.44 | 23.6% |
| ambiguous | 132,313 | **1.00** | **100.0%** |

Not "poor linkage": none. Every author the resolver flags ambiguous is a
fresh identity in every edition, by construction, so they can never have a
time series. That covers 132,313 career fact rows, 9.4% of the career table,
and inflates the author count to 818,667 when 350,908 of those rows (42.9%)
are fragments of people rather than people.

The cause is in `pipeline/identity.py`. When a `(surname, first_initial,
firstyr)` block holds more than one person, the resolver assigns a
deterministic **per-edition ordinal** from a content-ordered sort. That was
added to fix a real bug, two same-edition rows merging into one author when
both lacked an institution. It fixes that, and it also guarantees the same
person gets a different ordinal in the next edition whenever the sort order
shifts, which it does whenever anyone in the block changes institution or
enters or leaves.

Confirmed directly at the 2023 to 2024 boundary: 13,474 departures and
13,517 arrivals share an **exact** display name and an **exact** firstyr, and
every one of them is flagged ambiguous, in collision groups of 12 to 53.

## What it costs

**Labels.** An ambiguous author drops out every year by definition. In the
dropout test split roughly a third of the positives are this artefact, which
is why test ROC AUC is 0.814 against 0.936 on validation.

**The graph.** These author nodes carry exactly one fact row, so there is no
history for message passing to travel along.

**The dashboard.** The same authors render as a single point with no
trajectory. This predates the redesign.

**Fairness.** Large collision blocks are predominantly East Asian names
(`Zhu, Jianguo`, `Li, Min`, `Wang, Wei`), so the loss is concentrated on one
population rather than spread evenly.

## The 2024 boundary, separately

| edition | retention | new entrants |
|---|---|---|
| 2021 | 85.4% | 17.1% |
| 2022 | 84.5% | 17.3% |
| 2023 | 85.5% | 17.2% |
| **2024** | **81.4%** | **20.2%** |

2024 shows excess departures (~10,800 over trend) and excess arrivals
(~9,300 over trend) together, which is the signature of one person leaving
under an old name and arriving under a new one. Of the 40,436 departures,
86.4% have a 2024 arrival sharing surname and first initial, and 24,381 also
agree on firstyr to within a year.

That pool is not safe to merge on names alone. Among those near-twins sit
both `Kennedy, P. G.E. -> Kennedy, Peter G.E.` (the same person) and
`Wilson, James G. -> Wilson, John D.` (two people).

## There is a strong internal signal for linkage

Measured over 957,429 consecutive-edition observations of unambiguous
authors, so these are real trajectories of real people:

| signal | behaviour |
|---|---|
| composite score `c` | median change **0.42%**, 90th percentile 4.21% |
| h-index | never decreases in **98.8%** of steps, median +1, 99th pct +8 |
| paper count `np` | never decreases in 92.0%, median +3 |
| institution | unchanged in 72.3% |

`c` changing by less than half a percent a year is close to a fingerprint.
Within a block of 53 people sharing a name and a firstyr, matching each 2023
row to the 2024 row that continues its `c` and `h` is a well-posed
assignment problem, not a guess.

## Recommendation

Fix linkage inside the block before reaching for an external source.
It is cheaper, it needs no API budget, it targets the 132,313 rows directly,
and it can be validated against the 957,429 unambiguous trajectories we
already trust. OpenAlex then becomes the independent check on the result
rather than the mechanism, which is also the honest way to report a precision
figure.
