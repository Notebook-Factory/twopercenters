# Latency benchmark

`bench/latency.py` measures the two interactions a person actually feels in
the dashboard: typing into the author dropdown (typeahead) and picking an
author (fetch). `bench/build_legacy_index.py` reproduces the blob-era
Elasticsearch indices (`career`, `singleyr`) directly from `data_clean/` so
the "before" numbers can be measured locally, without the original dokku host
or the composite pickles that `elasticSearchIdx.py` expects (see the
docstring in `bench/build_legacy_index.py` for why those pickles aren't used).

## Reproducing the baseline

```bash
docker compose up -d --wait
ES_URL_LOCAL=http://localhost:9201 .venv/bin/python bench/build_legacy_index.py
ES_URL_LOCAL=http://localhost:9201 .venv/bin/python bench/latency.py --mode legacy --out bench/baseline.json
```

`--mode legacy` wires the typeahead/fetch phases to `bench/_legacy_es.py`, a
pinned copy of `citations_lib.utils.get_es_results` / `es_result_pick` as they
read at commit `9261573`, the last commit before the dashboard's Postgres
migration. That pin exists because `citations_lib.utils` itself has since
been migrated (`get_es_results` now queries the `authors` alias with a
filtered `_source`; `es_result_pick('data', ...)` now reads Postgres instead
of decompressing a blob) -- importing straight from `citations_lib.utils` for
"legacy" mode would silently measure the new stack twice under two labels.
`--mode current` wires the same two phases to the current, post-migration
`citations_lib.utils`, exactly as `pages/` calls it today.

## RULING R14: the original baseline was under-sampled

The 2026-09-13 baseline below used 6 search terms x 5 repeats. At that
sample size p95 is close to a single observation: running the identical
legacy code against identical data twice gave typeahead p50 11.46ms then
9.32ms (stable), but typeahead p95 40.31ms then 19.49ms and fetch p95
30.96ms then 48.87ms -- a 2x swing in both directions from noise alone. A
gate compared against that baseline would pass or fail at random.

`bench/baseline.json` (6 terms x 5 repeats) is kept as-is, as a historical
record of the first measurement. It is not used for the acceptance gate.
The gate instead compares two new files, both taken with 12 terms x 20
repeats:

- `bench/baseline_resampled.json` -- the legacy path (`--mode legacy`),
  re-measured at the higher sample size, against the same untouched
  `career`/`singleyr` indices.
- `bench/after.json` -- the current, post-migration path (`--mode current`).

### Search terms (`DEFAULT_TERMS` in `bench/latency.py`)

| term | why |
|------|-----|
| `an`, `jo` | 2-character prefixes; each matches hundreds of authors |
| `smi`, `wan` | 3-character prefixes; each matches thousands |
| `smith`, `johnson`, `chen`, `garcia`, `ioannidis` | full surnames of varying frequency (5,164 / 3,258 / 10,000+ / 901 / distinctive) |
| `müller` | a name carrying a diacritic |
| `smtih`, `ionnidis` | deliberate typos of `smith` / `ioannidis`, so the `fuzziness: "auto"` path is actually exercised, not just the exact-match path |

### Gate

- p50 (typeahead and fetch): the new stack must match or beat the legacy
  number, strictly. No tolerance.
- p95 (typeahead and fetch): a regression is allowed up to 25% over the
  legacy number; beyond that, it fails.

### Re-measured baseline vs. current stack (2026-09-13, 12 terms x 20 repeats)

| metric | legacy (`baseline_resampled.json`) | current (`after.json`) | delta | gate | verdict |
|---|---:|---:|---:|---|---|
| typeahead p50 | 5.72 ms | 6.69 ms | +0.97 ms (+17%) | match or beat | **FAIL** |
| typeahead p95 | 12.23 ms | 12.87 ms | +0.64 ms (+5%) | <=25% | pass |
| fetch p50 | 10.25 ms | 15.03 ms | +4.78 ms (+47%) | match or beat | **FAIL** |
| fetch p95 | 19.17 ms | 28.60 ms | +9.43 ms (+49%) | <=25% | **FAIL** |

A second back-to-back run (12x20 each, not saved as a separate file) showed
the same pattern: legacy typeahead p50 5.55ms vs. current 6.25ms (+13%),
legacy fetch p50 9.08ms vs. current 14.06ms (+55%). The typeahead p50
regression is small in absolute terms (about 1ms) but consistent across both
runs, not noise. The fetch p50 regression is large and consistent in both
runs: this is the Postgres round trip the migration plan expected to cost
something, landing at roughly 50% over the old blob-decompression path
rather than "match or beat."

**Verdict: FAIL. Status: BLOCKED**, per RULING R14 ("if the gate fails, do
not adjust the gate; report the numbers and stop").

Remedies checked, in the order the brief names them:

1. `_source` filtering on the typeahead query -- already present
   (`citations_lib/utils.py`, `_SOURCE_FIELDS`, restricting the ES response
   to 7 fields). No change available here; typeahead's regression is not a
   `_source` problem.
2. A covering index on `career_metrics (author_id, edition_id)` -- already
   exists (`career_metrics_author_id_edition_id_key`, a unique btree on
   exactly those two columns, plus `career_metrics_author_idx` /
   `singleyr_metrics_author_idx` on `author_id` alone). `EXPLAIN ANALYZE` on
   the actual `_author_rows` query (author_id -> 6 rows, 4 left joins to
   institutions/fields/subfields) shows it already uses
   `career_metrics_author_idx` via an index scan and completes in 1.8ms
   execution / 2.4ms planning. The index the brief names is already in
   place and the query is already fast; adding another index would not
   change this.
3. A narrow denormalized table -- not attempted. The brief allows this only
   "if [the covering index] is insufficient," which is the case here, but
   this is a schema-level design decision (a new table, a new migration, a
   new invalidation story) rather than a benchmarking task, so it was left
   for an explicit follow-up rather than done unilaterally inside this task.

No files outside `bench/` were changed. The regression is architectural: the
new fetch path makes two separate Postgres round trips (career and
singleyr), each with 4 joins, in place of one blob decompression; that cost
is real and reproducible, not a missing index.

### Machine noise during measurement

Both measurement runs were taken with Docker Desktop running an unrelated
project's containers alongside `twopercenters-postgres-1` and
`twopercenters-elasticsearch-1`: `insights-clickhouse` (~5-7% CPU),
`dbt-test-clickhouse` (~7-9% CPU), plus `insights-grafana`/`insights-proxy`/
`insights-pdf-service` at low/idle CPU. Load average was 3.8-5.3 over the
measurement window. Nothing was stopped for the run (stopping another
project's containers was out of scope), but the two back-to-back
legacy/current runs showed the same direction and rough magnitude of
regression, which is evidence the numbers above are not an artifact of that
background load.

Note: the checked-in `.env` in this environment had `ES_URL_LOCAL` pointing at
a stale Docker-internal address left over from an earlier run
(`172.17.0.3:9200`), not `localhost:9201`. Passing `ES_URL_LOCAL` on the
command line overrides it without needing to edit `.env` (a gitignored file
this task's scope doesn't include).

## Baseline: 2026-09-13

- Machine: macOS 15.5, arm64 (Apple Silicon), `Darwin 24.5.0`
- Elasticsearch: 7.17.23 (Docker, `localhost:9201`), populated by
  `bench/build_legacy_index.py` from `data_clean/version-{1,2,3,5}` (the four
  editions the deployed dashboard contains; version 4 is superseded by 5)

Index sizes right after indexing (`curl -s localhost:9201/_cat/indices?v&bytes=mb`):

```
health status index            uuid                   pri rep docs.count docs.deleted store.size pri.store.size
green  open   .geoip_databases pyq0kEm8S2eCmoYB-ElGQg   1   0         43            0         39             39
yellow open   career           HizHF_YYT0-wDXx0DfHWDQ   1   1     270910            0        357            357
yellow open   singleyr         tj9hPL_PSRyrD02duXaUIw   1   1     285533            0        330            330
```

career + singleyr = 687 MB, matching the ~700MB expected across both indices.

Measured latency (`bench/baseline.json`, `--mode legacy`, 6 typeahead terms x
5 repeats each = 30 typeahead calls / ~30 fetch calls):

| metric              | value (ms) |
|---------------------|-----------:|
| typeahead p50        | 11.46 |
| typeahead p95        | 40.31 |
| fetch p50             | 15.25 |
| fetch p95             | 30.96 |

These are the numbers the relational-core redesign must match or beat.
