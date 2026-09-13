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

`--mode legacy` wires the typeahead/fetch phases to
`citations_lib.utils.get_es_results` / `es_result_pick` against the
`career`/`singleyr` indices, exactly as `pages/` calls them today.
`--mode current` is meant for the post-migration lookup path once it exists;
see the note in `bench/latency.py` about what happens when it doesn't yet.

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
