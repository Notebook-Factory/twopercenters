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

### Re-measured baseline vs. current stack, before any remedy (12 terms x 20 repeats)

| metric | legacy (`baseline_resampled.json`, first cut) | current (before remedies) | delta | gate | verdict |
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
runs.

## Remedies applied (see below), then final measurement

`bench/baseline_resampled.json` and `bench/after.json` on disk hold the
**final**, post-remedy pair, re-measured together right after remedy 1
landed:

| metric | legacy (final) | current (final, after remedy 1) | delta | gate | verdict |
|---|---:|---:|---:|---|---|
| typeahead p50 | 5.55 ms | 4.76 ms | -0.79 ms (-14%) | match or beat | **PASS** |
| typeahead p95 | 12.23 ms | 7.83 ms | -4.40 ms (-36%) | <=25% | pass |
| fetch p50 | 8.38 ms | 13.30 ms | +4.92 ms (+59%) | match or beat | **FAIL** |
| fetch p95 | 17.01 ms | 19.28 ms | +2.27 ms (+13%) | <=25% | pass |

Typeahead now matches or beats legacy on both p50 and p95. Fetch p95
happens to land inside the 25% band on this run (it swung 23-49% across
earlier runs, consistent with R14's point that p95 is noisy even at
12x20), but **fetch p50 fails in every run taken**, before and after
remedy 2 was investigated (46-59% over legacy, never close to parity):
this is the one number that has been stable and damning throughout.

## Remedies applied

### Remedy 1 (typeahead): `size` 100 -> 30 in `get_es_results`

`citations_lib/utils.py`'s `_SOURCE_FIELDS` filtering was already present
and was not the cause. The actual causes: the unified `authors` alias holds
818,667 documents against the legacy `career` index's 270,910, so the same
fuzzy `multi_match` scores three times as many candidates; and a caller
requesting both kinds (the typeahead dropdown, and the radio-enabling
callback in `callback_templates.py`) used to get at most 100 rows total
(one legacy ES query spanning two indices), but against the single alias it
could get up to 100 hits x 2 kinds = 200 rows built and sorted in
`get_es_results`. Neither caller needs anywhere near 100 relevance-ranked
candidates, so `size` was reduced to 30 (`citations_lib/utils.py`,
`get_es_results`). Fuzziness is untouched.

Before/after (12x20, current stack only, same terms):

| metric | before remedy 1 | after remedy 1 | change |
|---|---:|---:|---:|
| typeahead p50 | 6.92 ms | 4.54 ms | -34% |
| typeahead p95 | 11.41 ms | 7.01 ms | -39% |
| fetch p50 | 15.44 ms | 13.84 ms | -10% (get_es_results is also used by fetch) |
| fetch p95 | 25.05 ms | 20.27 ms | -19% |

This alone took typeahead from failing to passing both p50 and p95 against
the legacy baseline (see final table below). 32 tests in
`tests/test_queries.py` and `tests/test_search_index.py` were re-run after
the change and pass; the full 108-test suite was re-run afterward and also
passes.

### Remedy 2 (fetch): checked, not changed

**(a) Covering index.** `career_metrics` and `singleyr_metrics` already
carry `(author_id, edition_id)` as a unique btree
(`career_metrics_author_id_edition_id_key`), plus a standalone
`career_metrics_author_idx` on `author_id`. `_author_rows`'s query selects
`m.*` (every column of the table, ~50 of them) joined to
institutions/fields/subfields, so a true covering index would need to
include essentially the whole row. Tested directly: `create index ...
include (<30 metric columns>)` on `career_metrics` -- Postgres refused a
32-column include list at the full column count ("cannot use more than 32
columns in an index"), so a fully covering index for this query is not
achievable at all. Built a partial one (2 key + 30 include columns) anyway
to see whether it helped: `EXPLAIN (ANALYZE, BUFFERS)` on the same
`_author_rows`-shaped query showed the planner still uses
`career_metrics_author_idx` (an index-only scan is impossible while any
selected column is missing from the index), execution time unchanged at
~1.8-2.3ms, planning time slightly higher. Dropped the index afterward;
nothing was kept.
**(b) Round trips.** `_author_rows` already issues one query per kind
(`where author_id = any(%s)`, no per-edition looping) -- already optimal,
nothing to change.

Neither remedy reduced fetch latency, because the query itself was already
fast (~1-2ms) and not index-only-scannable given its column list; the
remaining fetch cost is two additional Postgres round trips (one per kind)
that the blob-era path did not have, each carrying its own network/psycopg
overhead on top of query execution. This is the structural cost of leaving
blob storage the migration set out to accept, not a missing index.

**(c) Denormalized table -- not attempted.** Permitted by the brief only if
(a) and (b) are insufficient, which they are, but building one is a
schema-level decision (new table, new migration, new invalidation story)
that was left for explicit follow-up rather than done unilaterally here.

No files outside `bench/` and `citations_lib/utils.py` (the `size` change)
were changed; the covering-index experiments were created and dropped
directly against the local database, no migration file was added.

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

## The paired run, and why the fetch figure is measured twice

`--mode both --warmup N` measures both stacks in one process, interleaved
term by term, after warming each with the same terms and the same number of
passes. That removes the drift that made the legacy baseline fall on every
re-measurement (Elasticsearch's filesystem cache and the OS page cache held
more of the indices each time), and it means machine load over the run lands
on both sides equally instead of on whichever was measured second.

Warming both stacks equally is right for the filesystem caches. It was
**wrong** for the current stack's per-author memoisation, and for a while the
harness got that wrong without saying so. `warm()` calls `fetch_fn(hits[0])`
for every term, which fills `citations_lib.utils._author_rows`
(`lru_cache(maxsize=2048)`) with exactly the authors the measurement loop
then fetches, 20 times each. Every recorded current-stack fetch was a Python
dictionary hit. The legacy stack has no equivalent memo: it makes an HTTP
round trip and a base64+zlib decompress on every single call, always. The
reported 2.49ms "fetch p50" was a cache-hit number being compared against
legacy's real work.

So `measure_both` now records the current fetch twice per iteration:

- **`current_fetch_*` (cold).** `_author_rows.cache_clear()` runs before each
  recorded fetch, outside the timed region, so every sample does the work a
  user picking a previously-unviewed author causes. **This is the gate**, and
  it is the only figure comparable to legacy.
- **`current_fetch_warm_*` (warm).** The same fetch immediately afterwards
  with the memo intact: what a user re-viewing the author they just looked at
  experiences. True, useful, not the gate.

Only the per-author memo is cleared. `_maxima`, `_editions` and
`_column_names` are cached once per process for the whole dataset rather than
per author, so a real user pays them once at the first fetch ever; clearing
them each time would invent a cost the dashboard does not have. Nothing is
cleared on the legacy side, because the legacy code has nothing of the kind
to clear: the point is to remove an advantage, not to add a handicap.

### Final gate (12 terms x 20 repeats, `--warmup 2`, `bench/paired.json`)

| metric | legacy | current (cold) | delta | gate | verdict |
|---|---:|---:|---:|---|---|
| typeahead p50 | 6.64 ms | 5.62 ms | -15% | match or beat | **PASS** |
| typeahead p95 | 10.61 ms | 9.51 ms | -10% | <=25% | **PASS** |
| fetch p50 | 9.81 ms | 5.62 ms | -43% | match or beat | **PASS** |
| fetch p95 | 27.52 ms | 9.92 ms | -64% | <=25% | **PASS** |

Three consecutive runs, so the cold figure can be judged against its own
spread rather than one sample:

| run | legacy fetch p50 | current fetch p50 (cold) | current fetch p50 (warm) | legacy ta p50 | current ta p50 |
|---|---:|---:|---:|---:|---:|
| 1 | 13.07 | 5.77 | 3.45 | 7.83 | 6.22 |
| 2 | 10.89 | 6.18 | 3.81 | 7.19 | 5.64 |
| 3 | 9.81 | 5.62 | 3.46 | 6.64 | 5.62 |

The cold fetch beats legacy in all three, by 43-56%. The warm figure, 3.5ms,
is roughly 40% faster again than cold; it is reported for what it is and
nothing is decided on it.
