# Author identity in the Ioannidis top-2% citation databases: four failure modes and their repair

**Draft preprint. All figures were measured against the published data and are
reproducible from the code cited in each section.**

## Abstract

The Ioannidis/Elsevier "top 2% of scientists" databases are among the most
widely used bibliometric resources in research evaluation. They are published
as annual spreadsheets and identify authors by a formatted name string alone.
Working from all eight published versions, covering data years 2017 to 2024
and 2,730,673 author-edition rows, we document four properties of the
published data that make longitudinal use hazardous, and a fifth that arises
from the obvious way of working around the first.

None of these is a defect in the underlying citation analysis. They are
consequences of what the published artefact carries and omits, and of
decisions any reanalyst must make to join editions together. We report each
with the measurement that establishes it, describe the repair we implemented,
and quantify what the repair changed. One repair we attempted, measured, and
did not ship; we report that too, because the reason it failed is
informative.

The central result is methodological rather than bibliometric. After
repairing author identity, a graph neural network's accuracy at predicting
which authors leave the list **fell** from 0.814 to 0.687 ROC AUC. The fall
is the improvement: before the repair, a single binary flag recording our own
resolver's confusion scored 0.776 on the same task by itself. Most of the
apparent predictive skill was the model detecting an artefact of the data
preparation. We argue that a trivial-feature baseline of this kind should
accompany any predictive result on this dataset.

---

## 1. The data

Eight versions are published on the Elsevier Data Repository under
`doi:10.17632/btchxktzyw`, from 2019-07-06 to 2025-09-19, covering data years
2017 to 2024. Version 4 is superseded by version 5, which corrects it. Of the
50 files across all versions, 17 are author tables; excluding the superseded
version, 15 are in scope, totalling 2,730,673 rows across two kinds of table,
career-long and single-year.

Each version was downloaded and verified against a SHA-256 checksum recorded
per file, because no such manifest is published alongside the data and the
prior reanalysis we started from had lost the provenance of its own inputs.

### 1.1 There is no author identifier, in any edition

Every edition from 2017 to 2024 identifies authors by `authfull` alone, a
formatted name string. There is no Scopus Author ID, no ORCID, no identifier
of any kind. We checked this directly across all fifteen editions.

This is worth stating precisely, because it is easy to misattribute. Scopus
does carry ORCID: Scopus author profiles link to ORCID and Elsevier operates
that integration. The identifier exists upstream and is removed at
publication. The FAQ shipped with versions 7 and 8 is explicit that the rows
are Scopus author profiles and that "the published version reflects Scopus
author profiles at the time of calculation". So a stable identity was used to
compute every number in the file and was then discarded, leaving the
profile's preferred name as of the calculation date as the only handle.

Everything that follows is a consequence of that single editorial decision.

---

## 2. Failure mode one: the 2024 name expansion

Between the 2023 and 2024 editions, 90,755 author names changed string form,
because Scopus preferred names were expanded from abbreviated to full given
names:

```
Severinghaus, J. W.   ->  Severinghaus, John Wendell
Dahmen, U.            ->  Dahmen, Ulrich
Kennedy, P. G.E.      ->  Kennedy, Peter G.E.
Bostwick, David       ->  Bostwick, David G.M.D.
```

This is not attrition. The names absent from 2024 have a median rank of
111,000 against 108,354 for those present, so they are distributed like
everyone else.

Exact-name overlap between consecutive editions runs at 79 to 85 percent for
every pair from 2017 onward and collapses to **57.7 percent** at the
2023-2024 boundary. Any analysis keyed on the name string loses roughly forty
percent of all author time series at that point.

**Repair.** Block on `(surname, first initial, firstyr)` rather than on the
full name. `firstyr`, the year of an author's first indexed publication, is a
property of a career rather than of current circumstances: it is identical
for 94 to 97 percent of exactly-matched names across every edition pair,
where institution manages only 69 to 84 percent. The published FAQ explains
the latter: "Scopus uses a machine learning approach to select only one
affiliation from each author, based on the most recently published papers."
Country was tested as a fourth component and rejected, because researchers
relocate and adding it cost matches.

This restores the 2023-2024 boundary to 85.2 percent, inside the range every
other boundary reaches naturally.

One implementation detail is load-bearing and was initially wrong in our own
code. The blocking key must split the raw name on the comma *before*
normalising either side. Normalisation strips punctuation, including the
comma that separates surname from given name, so normalising first and then
splitting on whitespace treats a compound surname as its first token alone:
"van der Berg, Jan" becomes surname "van", initial "d". This affected 4,719
of 230,333 authors (2.05 percent) in a single edition, concentrated in Dutch,
German, Spanish and Arabic name forms.

---

## 3. Failure mode two: names that a name cannot separate

Blocking is necessary but not sufficient. Within the 2021 career edition,
194,983 rows carry 191,751 distinct names, and 5,722 rows participate in a
name collision. These are two people:

```
Abraham, Edward   University of Miami Miller School of Medicine  usa  rank 2,043
Abraham, Edward   Dragonfly Data Science                         nzl  rank 127,910
```

Adding `firstyr` reduces rows in collision from 5,722 to 325; adding
institution as well reduces it to 30. A residue always remains, and it is not
evenly distributed: the largest blocks are predominantly East Asian names,
where `Zhu, Jianguo` or `Li, Min` with the same first publication year can
denote dozens of distinct researchers.

Two rules govern what may be done with such a block. Two rows in the same
edition are two different people and must never be merged. Nothing may be
dropped; what cannot be resolved must become a separate author, flagged.

### 3.1 The obvious implementation is worse than it looks

Our first implementation satisfied both rules by giving every observation in
an ambiguous block its own identifier, minted per edition. This keeps
same-edition rows apart, which is correct, and it guarantees that the same
person receives a different identifier in the next edition, which is
catastrophic and silent.

Measured across the whole dataset:

| | authors | mean editions each | appear exactly once |
|---|---|---|---|
| unambiguous | 286,105 | 4.44 | 23.6% |
| ambiguous | 132,313 | **1.00** | **100.0%** |

Not poor linkage: none. Every author the resolver flagged ambiguous existed
in exactly one edition, by construction. That covered 132,313 career rows,
9.4 percent of the career table, and inflated the author count to 818,667
when 224,287 of those records were fragments of people rather than people.

The consequences are not confined to analysis. Those authors render in any
dashboard as a single data point with no trajectory; their history is
unavailable to any method that reads the relational structure; and because
the large blocks are predominantly East Asian names, the loss falls on one
population rather than spreading evenly.

### 3.2 Repair: match on the career, not on the name

A name that cannot separate two people is not the only evidence available.
Measured over 957,429 consecutive-edition observations of authors that the
name *could* separate, and which therefore have known trajectories:

| signal | behaviour between consecutive editions |
|---|---|
| composite score `c` | median change **0.42%**, 90th percentile 4.21% |
| h-index | never decreases in **98.8%** of steps, median +1 |
| paper count `np` | never decreases in 92.0% |
| field | unchanged 97.9% |
| country | unchanged 97.3% |
| subfield | unchanged 96.3% |
| institution | unchanged 72.3% |

A composite score that moves by less than half a percent a year is close to a
fingerprint. We therefore treat the block as a rectangular assignment
problem: each observation in edition *t* is matched to at most one
observation in edition *t+1*, minimising a cost built from the relative
change in `c`, an h-index monotonicity penalty, and mismatch penalties on
field, subfield, country and institution weighted by the stabilities above.
Pairings above a threshold are refused outright, so an author who genuinely
left is not forced onto a newcomer.

The one-to-one structure enforces the same-edition rule by construction
rather than by a check.

**Validation.** Taking authors whose 2023-to-2024 trajectory is already
known, forming synthetic blocks, and asking the matcher to recover the true
pairing:

| block size | random | `c` + h only | plus field, country, institution |
|---|---|---|---|
| 5 | 20.0% | 98.5% | 100.0% |
| 10 | 10.0% | 96.1% | 100.0% |
| 20 | 5.0% | 95.8% | 100.0% |
| 50 | **2.0%** | 88.5% | **100.0%** |

Because blocks drawn on `firstyr` alone may be separated by field or country
incidentally, we repeated the test with every block member sharing `firstyr`,
field **and** country, so that neither can discriminate:

| block size | random | `c` + h only | plus subfield, institution |
|---|---|---|---|
| 50 | **2.0%** | 89.4% | **99.5%** |

The metrics carry most of the result and the categorical attributes close the
remainder, mattering most exactly where blocks are largest.

Two limits on that figure should be stated. The synthetic blocks are
balanced, every member of edition *t* having a counterpart in *t+1*, whereas
real blocks gain and lose members; the implementation therefore uses a
rectangular assignment with a rejection threshold. And the members are drawn
from authors the resolver already separated by name, who may be easier than
the true residual.

### 3.3 One subtlety worth reporting: missing values are not neutral

A cost function that charges nothing for an absent attribute appears neutral
and is not, because a matching attribute also costs nothing. An absent value
therefore scores exactly as well as agreement, and a sparse record outranks a
genuine continuation.

This was not hypothetical. `Thomas, Stephen J.` in career-2019 has no
recorded country. With missing charged at zero, pairing him to the 2018
record of `Thomas, S. H.L.` cost 2.607 against 2.868 for `Thomas, S. H.L.`
himself, so one man's career was assigned to another. Given a country he
costs 3.807 and loses, correctly. Charging half a mismatch places an absent
value between agreement and disagreement, which is what "no evidence" should
mean, and raised hard-block recovery from 98.2 to 99.5 percent.

### 3.4 Result

Rebuilding all fifteen editions:

| | before | after |
|---|---|---|
| authors total | 818,667 | **594,380** |
| flagged ambiguous | 350,908 (42.9%) | 126,621 (21.3%) |
| ambiguous: mean editions each | **1.00** | **4.02** |
| ambiguous: appear exactly once | **100.0%** | **23.3%** |
| unambiguous: mean editions each | 4.44 | 4.44 |
| unambiguous: appear exactly once | 23.6% | 23.6% |

The comparison that matters is the ambiguous row against the unambiguous one.
At 4.02 editions against 4.44, and 23.3 percent appearing once against 23.6
percent, the previously unusable population is now statistically
indistinguishable from the population that was never broken, while the
control is untouched.

Edition-over-edition retention rises throughout:

| boundary | before | after |
|---|---|---|
| 2020 to 2021 | 85.4% | 94.1% |
| 2021 to 2022 | 84.5% | 93.3% |
| 2022 to 2023 | 85.5% | 94.6% |
| 2023 to 2024 | 81.4% | 90.6% |

The 2024 dip survives at roughly 3.5 points below the new trend. That is the
residual of the name expansion of Section 2, now visible in isolation rather
than masked by a general linkage failure.

---

## 4. Failure mode three: `rank` has no denominator on this list

`rank` is a natural field to display and a natural field to misread. It is
not a position within the published list. Sorting any career edition by
`rank` leaves the composite score `c` non-increasing in **100.00 percent** of
steps, so it is a strict global ordering over every scientist scored, not
over the ones published.

In career-2024 the largest rank is **1,210,493** against **230,333**
published rows, and **48,401 rows, 21 percent of the edition, carry a rank
larger than the entire list.** Those researchers appear because they are near
the top of a *subfield*: their median subfield rank is 2,311 out of a median
subfield of 131,858, and no published author falls below the top 5.6 percent
of their own subfield.

Presenting `rank` beside the size of the published edition therefore produces
a statement that cannot be true, and it is among the first things a reader
notices. We had done exactly this, rendering "ranked 1,210,493 among 230,333
researchers".

**Repair.** Report subfield standing, which is a pair the data supports:
`rank_subfield` is at most `subfield_count` in 100.00 percent of rows. Where
the global rank is reported it should be described as a position among all
scored scientists, whose exact size the published files do not state.

---

## 5. Failure mode four: an entire column missing from an entire edition

`firstyr` is absent from every row of singleyr-2017:

| edition | rows | `firstyr` missing |
|---|---|---|
| singleyr-2017 | 106,368 | **106,368 (100%)** |
| all fourteen others | 2,624,305 | 0 |

Version 1's single-year file does not carry the column. Because `firstyr` is
the third component of the blocking key (Section 2), every author in that
edition is blocked as `(surname, initial, NULL)` and cannot join their own
career record. John Ioannidis is two authors in the current data for this
reason alone: one carrying all eight career editions and six single-year
ones, the other carrying singleyr-2017 by itself.

**Attempted repair, not shipped.** First publication year is a property of a
person, not of a table, so the same publisher's career file for the same year
answers it. Of 104,656 distinct names in singleyr-2017, 69,517 also appear in
career-2017, and 68,315 of those resolve to a single `firstyr` there. An
implementation filled 68,890 rows.

It was reverted. Ambiguity in our design is a property of a whole
`(surname, initial, firstyr)` block, and the incremental loader relies on
that when it re-reads prior observations by their ambiguity flag. Changing
`firstyr` for rows of an already-loaded edition moves them between blocks,
and the rebuild produced blocks containing both confident and ambiguous
authors, which that fetch then reads incompletely. The failure surfaced as an
attempt to merge two distinct singleyr-2017 rows onto one author, refused by
a uniqueness constraint. The current database contains zero such mixed
blocks, confirming this is a fault the repair introduces rather than one it
reveals.

Doing it correctly requires backfilling before any edition is loaded, so that
no blocking key changes after the fact. We report the attempt because the
measurement stands even though the implementation did not, and because the
failure is a general caution: repairing a key that a pipeline has already
partitioned on is not a local change.

---

## 6. Why the model got worse, and why that is the point

The relational core supports predictive modelling directly. We trained the
reference heterogeneous graph neural network from the RelBench framework to
predict, for each author present in an edition, whether they will be absent
from the next one, training on editions up to 2022, validating on 2023 and
testing on 2024.

Before the identity repair, test ROC AUC was **0.814**. After it, **0.687**.

We had predicted the opposite. The explanation is a caution worth
generalising:

| | GNN test ROC AUC | `is_ambiguous` flag alone |
|---|---|---|
| before repair | 0.814 | **0.776** |
| after repair | 0.687 | **0.506** |

Before the repair, a single binary feature recording whether our own resolver
had failed on an author scored 0.776 on the dropout task by itself. An author
in an ambiguous block left the list every year *by construction*, so the
label and the flag agreed almost perfectly. The network's apparent skill was
overwhelmingly the detection of an artefact of data preparation. The dropout
positive rate fell from 18.6 to 9.4 percent once the artefact was removed:
roughly half of all recorded departures had never happened.

After the repair the same flag is worth 0.506, which is chance, and the
remaining 0.687 is signal about researchers who actually left.

A model scoring 0.81 on a corrupted label is worth less than one scoring 0.69
on a clean one, and the two are indistinguishable from the score alone. We
therefore recommend that any predictive result on this dataset be reported
alongside the score of a trivial feature derived from the analyst's own
preparation pipeline. Where such a feature performs comparably to the model,
the model is measuring the pipeline.

---

## 7. What remains open

**The residual of the name expansion.** After repair, the 2023-2024 boundary
retains 90.6 percent against a 94 percent trend. Roughly 10,000 researchers
at that boundary are still split between an old name and a new one.

**Blocks the metrics cannot separate.** Where two researchers in one block
have genuinely similar careers, the assignment has no evidence to work with.
The failure mode is conservative by design, an extra split rather than an
incorrect merge, because a split is recoverable and a merge is not.

**External validation.** Every figure in Section 3 is internal: the matcher
is validated against trajectories our own blocking established. An
independent anchor, OpenAlex being the obvious candidate given its
algorithmically disambiguated authors and ORCID links, would convert a
linkage rate into a measured precision and recall. We regard the figures here
as linkage rates and not as accuracy.

**`firstyr` in singleyr-2017**, per Section 5.

---

## 8. Recommendations to the publishers

One change would make almost all of this unnecessary: **publish the Scopus
Author ID.** It exists, it was used to compute every figure in the files, and
it is removed at publication. Its absence forces every downstream user to
reconstruct identity independently, imperfectly, and in mutually incompatible
ways, with errors that concentrate on a particular population of names.

Failing that, three smaller changes would each help materially:

1. **State the denominator for `rank`**, or publish the size of the scored
   population per edition.
2. **Carry `firstyr` in every table**, including single-year tables.
3. **Publish a file manifest with checksums**, so that provenance survives
   reanalysis.

## 9. Reproducibility

Every figure in this document is produced by code in the accompanying
repository: `pipeline/matching.py` for the assignment matcher,
`pipeline/identity.py` for blocking and resolution,
`pipeline/build_relational.py` for the loader, and `rdl/` for the predictive
modelling. `dataset_manifest.json` records the checksum of every source file.
The measurements supporting Sections 2 to 5 are collected in
`docs/identity-resolution-findings.md`.
