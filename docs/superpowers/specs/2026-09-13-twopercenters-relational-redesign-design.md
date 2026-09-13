# twopercenters: relational redesign and Kumo Relational demo

Date: 2026-09-13
Status: design approved, not yet implemented

## Why we are doing this

The dashboard at `twopercenters` visualises the Ioannidis/Elsevier "top 2% of
scientists" citation databases. It currently covers data years 2017 to 2021.
Three further editions have been published since (2022, 2023 and 2024) and need
to be added.

Adding them is not currently possible without a redesign, for two independent
reasons. The first is mechanical: the pipeline is five hand-run notebook stages
with absolute paths to a directory that no longer exists, and the storage layer
must be deleted and rebuilt in full to add a single year. The second is a
property of the data itself and is described under "The 2024 name break" below.

There is a second goal. The redesign is intended to double as a technical demo
of NVIDIA's Kumo Relational (Structured Data and Graph Models) running on this
dataset. Kumo Relational takes a multi-table database with primary and foreign
keys and a time column, and answers predictive queries zero-shot. That input
format is the same relational core the dashboard needs anyway, so the two goals
do not compete for effort.

## Non-goals

- Redesigning the dashboard's visual design or its analytical features.
- Recomputing or altering the published citation metrics. The upstream data is
  used as published.
- Replacing Elasticsearch. It keeps the job it is good at.
- Solving Scopus author disambiguation in general. We solve enough of it to
  link editions correctly, and frame the remainder as an open problem.

## What we established before designing

All of the following was measured against the real data during design, not
assumed. The numbers matter because several of them overturn assumptions the
current code is built on.

### The sources

Eight versions are published on the Elsevier Data Repository under
`doi:10.17632/btchxktzyw`, from 2019-07-06 to 2025-09-19, covering data years
2017 to 2024. Version 4 is superseded by version 5, which corrects it; both are
the 2021 data year. All 50 files across all 8 versions have been downloaded and
verified against SHA-256 checksums recorded in `dataset_manifest.json`.

Of those files, 17 are author tables. Excluding the superseded version 4, 15
are in scope, totalling 2,730,673 rows: 1,402,942 career and 1,327,731
singleyr. Career tables grow from 105,026 rows in 2017 to 230,333 in 2024.

Every workbook contains a `Key` sheet, which is the publishers' own data
dictionary for all 47 columns, and exactly one data sheet. This structural
property is what discovery keys on, replacing the hardcoded filename and
sheet-name lists in the original notebook.

### There is no author identifier, in any edition

Every edition from 2017 to 2024 identifies authors by `authfull` alone, a
formatted name string. There is no Scopus Author ID, ORCID, or any other
identifier column. Checked directly across all editions.

The FAQ shipped with versions 7 and 8 explains why this matters: "The databases
use Scopus data without further alteration... The published version reflects
Scopus author profiles at the time of calculation." The rows are Scopus author
profiles. A stable identity exists upstream and is discarded at publication,
leaving only the profile's preferred name as of the calculation date.

### The 2024 name break

Between the 2023 and 2024 editions, 90,755 author names changed string form,
because Scopus preferred names were expanded from abbreviated to full given
names:

    Severinghaus, J. W.   ->  Severinghaus, John Wendell
    Dahmen, U.            ->  Dahmen, Ulrich
    Terzija, Vladimir     ->  Terzija, Vladimir V.
    Cotran, Ramzi         ->  Cotran, Ramzi S.
    Ezugwu, Emmanuel O.   ->  Ezugwu, Emmanuel Okechukwu

This is not attrition. The names missing from 2024 have a median rank of
111,000 against 108,354 for those present, so they are distributed like
everyone else.

Exact-name overlap between consecutive editions runs at 79 to 85 percent for
every pair from 2017 onwards, and collapses to 57.7 percent at the 2023-2024
boundary. Loading the 2024 edition into the current `authfull`-keyed design
would break roughly 40 percent of all author time series. This is the reason
the redesign is a prerequisite for adding the new data rather than a cleanup
that can follow it.

### Same-name collisions are real and rows are currently being dropped

In the 2021 career table, 194,983 rows carry 191,751 distinct names. 5,722 rows
participate in a name collision. These are different people:

    Abraham, Edward   University of Miami Miller School of Medicine  usa  rank 2043
    Abraham, Edward   Dragonfly Data Science                         nzl  rank 127910

`create_composite_dict` keeps only `selected_data[0]` from each group, so one of
each pair is silently discarded and which one survives depends on row order.

### `firstyr` is the disambiguating field

Within the 2021 career edition, rows in collision fall from 5,722 on `authfull`
alone, to 325 adding `firstyr`, to 30 adding institution.

Across editions, matching on surname plus first initial plus `firstyr` recovers
the 2023-2024 break:

| Match key | Linked authors across 2023-2024 |
|---|---|
| `authfull` exact | 122,897 (57.7%) |
| surname + first initial | 129,751 |
| surname + first initial + `firstyr` | 181,334 (85.2%) |
| surname + initial + `firstyr` + country | 180,493 |

85.2 percent restores that boundary to the 79-85 percent range that every other
consecutive pair achieves naturally.

Adding country makes it slightly worse, because researchers relocate.
`firstyr` is identical for 94 to 97 percent of exactly-matched names across
every edition pair; institution manages only 69 to 84 percent. The FAQ explains
the latter: "Scopus uses a machine learning approach to select only one
affiliation from each author, based on the most recently published papers."

### Schema drift across editions

Metric column names embed the data year: `np6017`, `nc9617`, `h17`, `hm17` in
2017 become `np6024`, `nc9624`, `h24`, `hm24` in 2024. This is the sole reason
`standardize_col_names` exists.

Version 7 introduced a genuine schema change rather than a rename: `np60XX_d`
and `nc96XX_d`, present in versions 3 through 6, are replaced by three
retraction columns, taking the column count from 46 to 47:

    np6024_rw      papers marked as Retraction in RWDB
    nc9624_to_rw   cites to this author's retracted papers
    nc9624_rw      cites received from any retracted paper

The 2017 edition additionally uses an entirely different field taxonomy
(`sm-1`, `name1`, `frac1`) from every later edition (`sm-subfield-1`,
`sm-field`), and renames `npsf` to `cpsf` after 2017.

Editions are archival and immutable: the publishers state they are "published
annually in an archival form and will not [be] changed until the next annual
update". The `editions` table is therefore strictly append-only.

## Architecture

Three stores, each with one job.

**Elasticsearch keeps the author search box.** This is what makes the dashboard
feel instant and it is the one thing Elasticsearch is genuinely the right tool
for here. What changes is the document. Today each document carries a
zlib-compressed, base64-encoded blob of the author's entire history in a
`binary` field that Elasticsearch cannot search, aggregate or filter. The new
document holds only what the typeahead queries:

    author_id, authfull, name_normalized, inst_name, cntry, sm_field, years_present

The index drops from roughly 700 MB to tens of megabytes, a rebuild goes from
minutes to seconds, and adding an edition updates a small set of documents
instead of regenerating every blob. The existing fuzzy `multi_match` behaviour
is unchanged.

**Postgres is the system of record**, holding the metrics with real foreign key
constraints. After the user selects a name, the dashboard does a primary-key
lookup rather than decompressing a blob. Running on a dokku Postgres service in
production and a container locally, with the same schema and migrations in
both, which also removes the `ELASTICSEARCH_URL`-or-hardcoded-laptop-path
branching in `elasticSearchIdx.py` and `citations_lib/utils.py`.

**Parquet is the export** that Kumo Relational materialises its graph from,
written by `COPY ... TO` out of Postgres.

Because the foreign keys are declared and enforced in Postgres, the edges of
the Kumo graph are read off the schema rather than configured separately.

## Schema

    countries(country_code PK, name)
    institutions(institution_id PK, inst_name, country_code FK)
    fields(field_id PK, name)
    subfields(subfield_id PK, name, field_id FK)

    authors(author_id PK, authfull_display, name_normalized, surname,
            first_initial, firstyr, collision_group_size, is_ambiguous,
            first_data_year, last_data_year)

    editions(edition_id PK, mendeley_version, data_year, kind,
             observation_date, published_date, source_filename, sha256,
             superseded_by, columns_present)

    author_name_observations(observation_id PK, author_id FK, edition_id FK,
                             authfull_raw, resolution_method, is_confident)

    career_metrics(metric_id PK, author_id FK, edition_id FK,
                   institution_id FK, field_id FK, field_frac,
                   subfield_1_id FK, subfield_1_frac,
                   subfield_2_id FK, subfield_2_frac,
                   observation_date,
                   rank, c, h, hm, nc, np, nps, ncs, cpsf, ncsf, npsfl,
                   ncsfl, npciting, cprat, np_cited,
                   rank_ns, c_ns, h_ns, hm_ns, nc_ns, nps_ns, ncs_ns,
                   cpsf_ns, ncsf_ns, npsfl_ns, ncsfl_ns, npciting_ns,
                   cprat_ns, np_cited_ns,
                   self_pct, firstyr, lastyr,
                   rank_subfield, rank_subfield_ns, subfield_count,
                   np_rw, nc_to_rw, nc_rw, np_d, nc_d)

    singleyr_metrics(... identical shape ...)

    metric_maxima(edition_id FK, metric, max_value)

Design decisions and their reasons:

**The year leaves the column names.** `np6021` becomes `np`, `h21` becomes `h`,
`np6021 cited9621` becomes `np_cited`. The year lives in the row via
`edition_id`. This removes `standardize_col_names`, the `career_versions =
[1,1,2,3,5]` parallel lists, and the nine hardcoded year mappings currently
duplicated across `utils.py`, `author_vs_group_layout.py` and
`group_vs_group_layout.py`. Adding version 9 becomes an INSERT.

**Edition-specific columns are nullable.** `np_d` and `nc_d` are populated for
versions 3 to 6, the `_rw` columns for versions 7 and 8. `editions.columns_present`
records what each edition actually carried so that absence is data rather than
a crash.

**Career and singleyr are separate tables.** They measure different quantities:
career `np` counts papers since 1960, singleyr `np` counts one year. Separate
tables mean a query reads `career_metrics.c` without a filter and nobody can
accidentally average across two definitions.

**The log transform is not stored.** It is a presentation choice, currently
frozen into roughly half of the 1.9 GB of pickles. `metric_maxima` holds about
500 rows and the transform `log(x+1)/log(max+1)` is applied at render time.
Switching later to the publishers' own `Table_3_maxlog_*` values becomes an
UPDATE of 500 rows.

**Group aggregates become a materialized view.** The five-number summaries per
country, field and institution that `02_data_preproc_for_speed.ipynb` computes
by hand become a `group_metrics` materialized view defined in SQL.

**`observation_date` is December 31 of the data year**, not the Mendeley
publication date, because the data year is the semantic time and publication lag
varies from 10 to 20 months across editions. Kumo Relational requires a time
column to build a temporal graph.

## Author identity resolution

Identity is resolved with provenance, never assumed. `author_name_observations`
records the raw `authfull` exactly as published alongside the `author_id` it
resolved to, the method used, and whether the resolution was confident.

The resolution key is **surname + first initial + `firstyr`**, on the evidence
above.

Two hard constraints:

**Within an edition, one row is one person.** Each edition lists each author
exactly once, so two rows in the same edition are two different humans by
construction and must never merge. This makes the present `selected_data[0]`
behaviour a bug rather than a simplification.

**Nothing is dropped.** Authors that do not resolve confidently become separate
entities with `is_ambiguous` set, and the dashboard states that a name is shared
by several researchers, showing institution to distinguish them, rather than
silently picking one.

Resolution runs as a blocking step: block on surname plus first initial, then
within a block use `firstyr` to assign, then institution and field as
tiebreakers. Where a block contains multiple people in both of two editions, the
assignment is one-to-one within the block rather than independent per row.

**This is deliberately not a solved problem.** 85.2 percent is the rate at which
a deterministic rule links records; it is not a measured accuracy, because there
is no ground truth. Some of the 58,437 recovered links will be wrong and some
correct links are still missing. Turning it into precision and recall requires
either a hand-labelled sample or the OpenAlex linkage described below, and both
are in scope.

## Ingestion pipeline

Five hand-run notebook stages become four scripts, each with one job, each
runnable from a clean checkout.

1. `fetch_sources.py` (**built**) reads `dataset_manifest.json` and downloads all
   50 files, verifying SHA-256 and skipping what is already correct.
2. `clean_sources.py` (**built**) reproduces `01_data_pickling.ipynb` for every
   edition, discovering author tables by structure rather than filename.
3. `build_relational.py` (**to build**) normalises column names, resolves author
   identity, and loads Postgres. Emits Parquet for Kumo.
4. `build_search_index.py` (**to build**) writes the slim Elasticsearch
   documents, into a versioned index swapped behind an alias so the dashboard
   never sees a deleted index.

`verify_clean.py` (**built**) already demonstrates that stage 2 is faithful: all
18 pickles for versions 1, 2, 3 and 5 match the originals committed in
`qMRLab/no_cite-isfaction`. The nine raw tables are bit-identical. The nine
log-transformed tables agree to within 2 ULP on 872 of 7,799,196 float cells,
which is `np.log` rounding differently between numpy builds and not a difference
in what the code computes.

Stage 2 deliberately preserves two behaviours that are arguably wrong: the log
transform is applied to `rank`, `firstyr` and `lastyr` as well as to the
citation metrics, and the maximum comes from the data rather than the published
`Table_3_maxlog_*` files. Preserving them is what made the comparison
meaningful. Both become deliberate, testable decisions at stage 3.

## The Kumo Relational layer

Kumo Relational runs as an NVIDIA NIM and is driven either through the
`kumo-relational-client[relational]` package or through the `kumo-rfm-mcp` MCP
server, whose tools include `materialize_graph`, `predict`, `evaluate`,
`explain` and `get_mermaid`. It reads tables from CSV or Parquet.

### Two graph layers

The **core layer** is the schema above. Kumo reads the declared foreign keys as
edges.

The **enrichment layer** is OpenAlex, which publishes over 120 million
algorithmically disambiguated authors linked to ORCID where available, with
works, institutions and co-authorship, as a freely downloadable full snapshot.
Adding `openalex_authors`, `works` and `authorships` introduces author-to-author
co-authorship edges.

This is the single most valuable addition in the design. Without it the graph is
a star schema in which every path between two authors runs through an
institution or a field, which is thin relational context. Co-authorship turns it
into a network, which is the setting where relational deep learning has an
argument to make. OpenAlex also supplies the external anchor that turns the
entity resolution baseline into measured precision and recall.

Note the February 2026 OpenAlex pricing change: the API now requires a free key
with a daily allowance, so 230,000 authors should be linked from the bulk
snapshot, not the API.

### Predictive queries

Exact PQL syntax below is our reading of the documented grammar
(`FUNCTION(column, start, end, unit)`, units of hours, days or months, start
exclusive and end inclusive) and must be confirmed against the MCP server before
demonstration. Only the regression form is quoted verbatim in the docs we could
reach.

**1. Top-2% dropout.** The direct analog of their flagship churn case, and
competitive: remaining on the list is a threshold on rank within a subfield, so
the outcome depends on every other author.

    PREDICT COUNT(career_metrics.*, 0, 12, months) = 0
    FOR EACH authors.author_id
    WHERE COUNT(career_metrics.*, -12, 0, months) > 0

**2. Next-edition composite score.** Regression on `c`. Shown mainly in order to
say why it is the weakest of the four: career metrics are cumulative since 1960,
so next year's `c` is close to this year's `c`.

**3. Next affiliation.** Link prediction over institutions. Genuinely hard,
since affiliation is itself an ML guess at one of several and we measured it as
only 69 to 84 percent stable.

**4. Retraction-exposure backfill.** The centrepiece. The `_rw` columns exist
only for 2023 and 2024. Every earlier edition is empty, not because nothing was
retracted but because tracking began in 2024. Kumo supports missing value
imputation, so: impute retraction exposure for 2017 to 2022 and validate by
holding out 2023 and 2024 where the truth is known. A real question, a built-in
evaluation, and an output nobody currently has.

**5. Entity resolution as link prediction**, presented as the open problem
rather than a finished result. There is now a deterministic baseline of 85.2
percent on the hardest edition boundary, with a defined residual of roughly
31,000 unmatched authors plus the multi-person name blocks. The question put to
Kumo is specific and falsifiable: can link prediction over the relational graph
beat that baseline on the remainder?

### Agentic layer

`kumo-rfm-mcp` is an MCP server, so Claude Code drives it directly, and a
natural-language box in the dashboard becomes question to PQL to `predict` to
chart, with `explain` rendering the reasoning.

There appear to be two MCP surfaces: a documentation server at
`docs.nvidia.com/sdgm/_mcp/server` for AI clients, and the `kumo-rfm-mcp`
package exposing the predictive tools. Which is the supported path for a live
demo must be confirmed early, since it affects the demo's architecture.

## Verification and acceptance criteria

**Performance must not regress, and this is measured, not judged.** Before any
migration, record keystroke-to-dropdown and author-selection-to-chart latency on
the current deployment. The redesign must match or beat both.

The reasoning for expecting an improvement: the current typeahead issues
`size=100` with no `_source` filtering, so every keystroke returns 100 full
documents including 100 compressed blobs and discards all but the names. Slim
documents collapse that payload. The risk sits in the new Postgres round trip
for the per-author fetch. If that is the weak point, the fix is a narrow
denormalized table or a cache, not a return to blobs.

**Search quality must not regress.** `pg_trgm` was considered as an
Elasticsearch replacement and rejected in favour of keeping Elasticsearch.
Typeahead behaviour should be unchanged, since the query is unchanged.

**Ingestion is verified at each stage.** Stage 2 is already verified against the
committed originals. Stage 3 gets row-count reconciliation per edition against
the cleaned pickles, foreign key constraints enforced by Postgres, and a check
that no author row is dropped, which is the specific regression that
`selected_data[0]` represents today.

**Entity resolution is evaluated, not asserted.** A hand-labelled sample of a
few hundred cases, plus OpenAlex linkage, produce precision and recall. The
85.2 percent figure is reported as a linkage rate until then.

## Risks and open questions

- **PQL syntax for classification, link prediction and imputation is unverified.**
  Confirm against the MCP server before building the demo around specific queries.
- **Which MCP surface to use** is ambiguous in the documentation.
- **Eight annual snapshots is a coarse temporal graph.** PQL time units are
  hours, days and months, so a year is `12, months` and there are eight points.
- **Cumulative-metric leakage** makes naive regression targets trivially easy.
  Prefer competitive and threshold-based targets.
- **OpenAlex linkage is itself an entity resolution problem**, and a hard one. It
  may resolve fewer authors than hoped.
- **Pickles require pandas 1.5-era versions to read.** Stage 2's outputs were
  produced and verified with pandas 1.5.3 and numpy 1.26.4. Stage 3 should read
  them once and never depend on them again.
- **The 2017 edition's different field taxonomy** means its `sm-1`/`name1`
  columns need an explicit mapping to the later `sm-field`/`sm-subfield-1`
  scheme, or 2017 field data is marked unavailable. This decision is not yet
  made.

## Sequencing

1. Baseline the current dashboard's latency. Nothing else can start without it.
2. `build_relational.py`: schema, column normalisation, identity resolution,
   Postgres load, Parquet export.
3. `build_search_index.py`: slim documents, alias swap.
4. Migrate the Dash callbacks from blob decoding to Postgres queries.
5. Confirm PQL syntax and the MCP path; materialize the graph; run queries 1 to 3.
6. OpenAlex linkage; entity resolution evaluation.
7. Retraction-exposure backfill, the demo centrepiece.
8. Agentic layer in the dashboard.

Steps 1 to 4 deliver the dashboard improvement and the new data, and stand alone
if the demo never happens. Steps 5 to 8 deliver the demo and depend on 1 to 4.
