# twopercenters Relational Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blob-in-Elasticsearch store with a Postgres relational core so the 2022, 2023 and 2024 editions can be loaded without breaking author time series, while keeping the dashboard's search snappiness.

**Architecture:** Three stores, each with one job. Elasticsearch keeps the author typeahead but its documents lose the compressed blob. Postgres becomes the system of record with declared foreign keys. Parquet is exported for the Kumo Relational demo (plan 2). All dashboard access funnels through four functions in `citations_lib/utils.py`, which are reimplemented in place so no layout module changes.

**Tech Stack:** Python 3.10.14, Dash 2.15, Postgres 16, Elasticsearch 7.17.23, psycopg 3, pandas, pytest, docker-compose locally, dokku in production.

**Spec:** `docs/superpowers/specs/2026-09-13-twopercenters-relational-redesign-design.md`

## Global Constraints

- Python 3.10.14 (`runtime.txt`). The dokku buildpack refuses EOL versions.
- Elasticsearch 7.17.23 locally and in production, matching the existing dokku service.
- Postgres 16.
- The reading of existing `.pkl` files requires pandas 1.5.x and numpy < 2. This
  constraint applies ONLY to `build_relational.py` reading `data_clean/`. The Dash
  app itself must not depend on it.
- `citations_lib/utils.py` public function signatures must not change:
  `get_es_results(search_term, idx_name, search_fields, exact=False)`,
  `es_result_pick(result, field, nohit=[''])`,
  `get_es_aggregate(group, group_name, prefix)`,
  `base64_decode_and_decompress(encoded_data, flg=True)`.
- Version 4 of the source dataset is superseded by version 5 and is excluded everywhere.
- Every generated identifier is deterministic: re-running a build must produce the
  same `author_id` values. No random UUIDs, no autoincrement for author identity.
- No secrets in committed files. `DATABASE_URL` and `ELASTICSEARCH_URL` come from
  the environment (dokku sets both when services are linked).

---

## File Structure

**Create:**
- `docker-compose.yml` - local Postgres + Elasticsearch
- `Makefile` - `make up`, `make down`, `make build-all`, `make test`
- `db/migrations/001_schema.sql` - all tables, indexes, constraints
- `db/migrations/002_group_metrics.sql` - materialized view
- `db/migrate.py` - applies numbered migrations, tracks applied ones
- `db/connection.py` - single place that resolves `DATABASE_URL`
- `pipeline/column_map.py` - year-stamped column name -> canonical name
- `pipeline/identity.py` - author identity resolution
- `pipeline/build_relational.py` - loads `data_clean/` into Postgres, exports Parquet
- `pipeline/build_search_index.py` - slim Elasticsearch documents + alias swap
- `bench/latency.py` - typeahead and author-fetch latency harness
- `tests/test_column_map.py`, `tests/test_identity.py`, `tests/test_queries.py`,
  `tests/test_search_index.py`
- `requirements-dev.txt`

**Modify:**
- `citations_lib/utils.py:24-29` (connection setup), `:88-123` (`es_result_pick`,
  `get_es_aggregate`), `:125-156` (`get_es_results`), `:158-173`
  (`base64_decode_and_decompress`)
- `requirements.txt` - add `psycopg[binary]`, `pyarrow`
- `app.json` / dokku deploy notes in `README.md`

**Unchanged (deliberately):** every file in `citations_lib/` other than `utils.py`,
everything in `pages/`, `app.py`. If a task requires editing one of those, stop:
the seam has been broken and the design needs revisiting.

---

### Task 1: Local environment

**Files:**
- Create: `docker-compose.yml`, `Makefile`, `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Produces: a local Postgres reachable at `postgresql://twopct:twopct@localhost:5433/twopct`
  and Elasticsearch at `http://localhost:9201`. Non-default ports avoid clashing with
  anything already running.

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: twopct
      POSTGRES_PASSWORD: twopct
      POSTGRES_DB: twopct
    ports: ["5433:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U twopct"]
      interval: 5s
      retries: 20

  elasticsearch:
    image: elasticsearch:7.17.23
    environment:
      discovery.type: single-node
      ES_JAVA_OPTS: "-Xms1g -Xmx1g"
      xpack.security.enabled: "false"
    ports: ["9201:9200"]
    volumes: ["esdata:/usr/share/elasticsearch/data"]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:9200/_cluster/health || exit 1"]
      interval: 5s
      retries: 20

volumes:
  pgdata:
  esdata:
```

- [ ] **Step 2: Write `.env.example`**

```bash
# Local development. Copy to .env; .env is gitignored.
DATABASE_URL=postgresql://twopct:twopct@localhost:5433/twopct
ELASTICSEARCH_URL=http://localhost:9201
```

- [ ] **Step 3: Write the `Makefile`**

```makefile
.PHONY: up down logs test build-all

up:
	docker compose up -d --wait

down:
	docker compose down

logs:
	docker compose logs -f

test:
	pytest tests -v

build-all:
	python db/migrate.py
	python pipeline/build_relational.py data_clean
	python pipeline/build_search_index.py
```

- [ ] **Step 4: Bring it up and verify both services answer**

Run:
```bash
make up
psql postgresql://twopct:twopct@localhost:5433/twopct -c 'select version();'
curl -s http://localhost:9201/_cluster/health | python3 -m json.tool
```
Expected: Postgres prints `PostgreSQL 16.x`; Elasticsearch returns JSON with
`"status": "green"` or `"yellow"` (yellow is correct for a single node).

- [ ] **Step 5: Add `.env` to `.gitignore` if absent, and commit**

```bash
grep -qx '.env' .gitignore || echo '.env' >> .gitignore
git add docker-compose.yml Makefile .env.example .gitignore
git commit -m "build: local Postgres and Elasticsearch via docker-compose"
```

---

### Task 2: Latency baseline

The spec makes this a hard gate: the redesign must match or beat the current
numbers, and there is no way to know that without recording them first. The old
dokku host may not be reachable, so the baseline is measured against the current
design reproduced locally. That is also more reproducible than a one-off
measurement against production.

**Files:**
- Create: `bench/latency.py`, `bench/README.md`
- Test: `tests/test_latency_harness.py`

**Interfaces:**
- Produces: `bench.latency.measure(typeahead_fn, fetch_fn, terms) -> dict` with keys
  `typeahead_p50_ms`, `typeahead_p95_ms`, `fetch_p50_ms`, `fetch_p95_ms`, `n`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_latency_harness.py
import time
from bench.latency import measure


def test_measure_reports_percentiles_for_both_phases():
    def typeahead(term):
        time.sleep(0.002)
        return ["Ioannidis, John P.A."]

    def fetch(name):
        time.sleep(0.004)
        return {"c": 1.0}

    result = measure(typeahead, fetch, ["ioa", "ioan", "ioann"])

    assert result["n"] == 3
    assert result["typeahead_p50_ms"] >= 2.0
    assert result["fetch_p50_ms"] >= 4.0
    assert result["typeahead_p95_ms"] >= result["typeahead_p50_ms"]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_latency_harness.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'bench'`

- [ ] **Step 3: Implement `bench/latency.py`**

```python
"""Measure dashboard-facing latency for the two interactions users feel.

Phase one is keystroke-to-dropdown: the author typeahead. Phase two is
selection-to-chart: fetching one author's metrics. Both are measured the same
way before and after the migration, so the comparison is like for like.
"""
import statistics
import time


def _percentile(values, pct):
    ordered = sorted(values)
    index = min(int(round((pct / 100) * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[index]


def measure(typeahead_fn, fetch_fn, terms, repeats=5):
    typeahead_ms, fetch_ms = [], []

    for term in terms:
        for _ in range(repeats):
            started = time.perf_counter()
            hits = typeahead_fn(term)
            typeahead_ms.append((time.perf_counter() - started) * 1000)

            if hits:
                started = time.perf_counter()
                fetch_fn(hits[0])
                fetch_ms.append((time.perf_counter() - started) * 1000)

    return {
        "n": len(terms),
        "repeats": repeats,
        "typeahead_p50_ms": round(statistics.median(typeahead_ms), 2),
        "typeahead_p95_ms": round(_percentile(typeahead_ms, 95), 2),
        "fetch_p50_ms": round(statistics.median(fetch_ms), 2),
        "fetch_p95_ms": round(_percentile(fetch_ms, 95), 2),
    }
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `pytest tests/test_latency_harness.py -v`
Expected: PASS

- [ ] **Step 5: Record the "before" numbers**

Load the current design into the local Elasticsearch and measure it. This uses
the existing `elasticSearchIdx.py` unchanged, against the pickles produced by
`clean_sources.py` for versions 1, 2, 3 and 5 only, which is what the deployed
dashboard contains.

```bash
# The existing indexer expects composite pickles; point it at the originals
# from the qMRLab clone, which is what production was built from.
ES_URL_LOCAL=http://localhost:9201 python elasticSearchIdx.py
python bench/latency.py --mode legacy --out bench/baseline.json
```

Write `bench/baseline.json` into the repo. Record in `bench/README.md` the date,
the machine, and the exact index sizes from
`curl -s localhost:9201/_cat/indices?v`.

- [ ] **Step 6: Commit**

```bash
git add bench/ tests/test_latency_harness.py
git commit -m "test: latency harness and pre-migration baseline"
```

---

### Task 3: Database schema

**Files:**
- Create: `db/migrations/001_schema.sql`, `db/migrate.py`, `db/connection.py`
- Test: `tests/test_migrations.py`

**Interfaces:**
- Produces: `db.connection.connect() -> psycopg.Connection`, and the tables named in
  the spec. `db.migrate.apply_all(conn, migrations_dir)` returns the list of
  filenames applied this run.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrations.py
import os
import psycopg
import pytest
from db.migrate import apply_all

DSN = os.environ["DATABASE_URL"]


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as c:
        c.execute("drop schema public cascade; create schema public;")
        c.commit()
        yield c


def test_apply_all_creates_tables_and_is_idempotent(conn):
    first = apply_all(conn, "db/migrations")
    assert "001_schema.sql" in first

    tables = {
        r[0] for r in conn.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'public'"
        ).fetchall()
    }
    for expected in ["authors", "editions", "career_metrics", "singleyr_metrics",
                     "institutions", "countries", "fields", "subfields",
                     "author_name_observations", "metric_maxima"]:
        assert expected in tables

    second = apply_all(conn, "db/migrations")
    assert second == []


def test_career_metrics_rejects_orphan_author(conn):
    apply_all(conn, "db/migrations")
    conn.execute("insert into editions (edition_id, mendeley_version, data_year, "
                 "kind, observation_date) values ('career_2024', 8, 2024, "
                 "'career', '2024-12-31')")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("insert into career_metrics (author_id, edition_id, "
                     "observation_date) values ('nosuchauthor', 'career_2024', "
                     "'2024-12-31')")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `DATABASE_URL=postgresql://twopct:twopct@localhost:5433/twopct pytest tests/test_migrations.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Write `db/connection.py`**

```python
"""Single place that resolves the database URL.

dokku sets DATABASE_URL when a Postgres service is linked to the app. Locally it
comes from .env. There is deliberately no hardcoded fallback path: the previous
design's laptop-specific default is the bug this replaces.
"""
import os

import psycopg
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


def dsn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Locally: copy .env.example to .env and "
            "run `make up`. On dokku: `dokku postgres:link <service> <app>`."
        )
    return url


def connect():
    return psycopg.connect(dsn())
```

- [ ] **Step 4: Write `db/migrations/001_schema.sql`**

```sql
create table countries (
    country_code text primary key,
    name         text not null
);

create table institutions (
    institution_id text primary key,
    inst_name      text not null,
    country_code   text references countries(country_code)
);

create table fields (
    field_id text primary key,
    name     text not null
);

create table subfields (
    subfield_id text primary key,
    name        text not null,
    field_id    text references fields(field_id)
);

create table authors (
    author_id            text primary key,
    authfull_display     text not null,
    name_normalized      text not null,
    surname              text not null,
    first_initial        text not null,
    firstyr              integer,
    collision_group_size integer not null default 1,
    is_ambiguous         boolean not null default false,
    first_data_year      integer,
    last_data_year       integer
);

create index authors_name_normalized_idx on authors (name_normalized);
create index authors_block_idx on authors (surname, first_initial, firstyr);

create table editions (
    edition_id       text primary key,
    mendeley_version integer not null,
    data_year        integer not null,
    kind             text not null check (kind in ('career', 'singleyr')),
    observation_date date not null,
    published_date   date,
    source_filename  text,
    sha256           text,
    superseded_by    integer,
    columns_present  jsonb not null default '[]'::jsonb,
    unique (data_year, kind)
);

create table author_name_observations (
    observation_id    bigserial primary key,
    author_id         text not null references authors(author_id),
    edition_id        text not null references editions(edition_id),
    authfull_raw      text not null,
    resolution_method text not null,
    is_confident      boolean not null,
    unique (edition_id, authfull_raw, author_id)
);

create table metric_maxima (
    edition_id text not null references editions(edition_id),
    metric     text not null,
    max_value  double precision not null,
    primary key (edition_id, metric)
);
```

Then, for each of `career_metrics` and `singleyr_metrics`, the same shape. Write
both out in full; do not use a loop or a template, because the two tables are
allowed to diverge later and a reader must be able to see each one whole.

```sql
create table career_metrics (
    metric_id        bigserial primary key,
    author_id        text not null references authors(author_id),
    edition_id       text not null references editions(edition_id),
    institution_id   text references institutions(institution_id),
    field_id         text references fields(field_id),
    field_frac       double precision,
    subfield_1_id    text references subfields(subfield_id),
    subfield_1_frac  double precision,
    subfield_2_id    text references subfields(subfield_id),
    subfield_2_frac  double precision,
    observation_date date not null,

    rank integer, c double precision, h integer, hm double precision,
    nc bigint, np integer, nps integer, ncs bigint, cpsf integer,
    ncsf bigint, npsfl integer, ncsfl bigint, npciting bigint,
    cprat double precision, np_cited integer,

    rank_ns integer, c_ns double precision, h_ns integer, hm_ns double precision,
    nc_ns bigint, nps_ns integer, ncs_ns bigint, cpsf_ns integer,
    ncsf_ns bigint, npsfl_ns integer, ncsfl_ns bigint, npciting_ns bigint,
    cprat_ns double precision, np_cited_ns integer,

    self_pct double precision, firstyr integer, lastyr integer,
    rank_subfield integer, rank_subfield_ns integer, subfield_count integer,

    np_rw integer, nc_to_rw bigint, nc_rw bigint,
    np_d integer, nc_d bigint,

    unique (author_id, edition_id)
);

create index career_metrics_author_idx on career_metrics (author_id);
create index career_metrics_edition_idx on career_metrics (edition_id);
create index career_metrics_field_idx on career_metrics (field_id, edition_id);
create index career_metrics_cntry_idx on career_metrics (institution_id, edition_id);
```

Repeat verbatim for `singleyr_metrics`, changing only the table and index names.

- [ ] **Step 5: Write `db/migrate.py`**

```python
"""Apply numbered SQL migrations, once each, in filename order.

Deliberately not Alembic: this project has one schema, no branching history, and
adding a migration framework would be more machinery than the problem needs.
"""
import os
import sys

from db.connection import connect

TRACKING = """
create table if not exists schema_migrations (
    filename   text primary key,
    applied_at timestamptz not null default now()
)
"""


def apply_all(conn, migrations_dir):
    conn.execute(TRACKING)
    applied = {r[0] for r in conn.execute(
        "select filename from schema_migrations").fetchall()}

    ran = []
    for filename in sorted(os.listdir(migrations_dir)):
        if not filename.endswith(".sql") or filename in applied:
            continue
        with open(os.path.join(migrations_dir, filename)) as handle:
            conn.execute(handle.read())
        conn.execute("insert into schema_migrations (filename) values (%s)",
                     (filename,))
        ran.append(filename)

    conn.commit()
    return ran


if __name__ == "__main__":
    with connect() as connection:
        for name in apply_all(connection, "db/migrations"):
            print(f"applied {name}")
```

- [ ] **Step 6: Run the tests and watch them pass**

Run: `DATABASE_URL=postgresql://twopct:twopct@localhost:5433/twopct pytest tests/test_migrations.py -v`
Expected: both tests PASS. The second proves foreign keys are enforced, which is
what makes the Kumo graph readable off the schema in plan 2.

- [ ] **Step 7: Commit**

```bash
git add db/ tests/test_migrations.py
git commit -m "feat: relational schema with enforced foreign keys"
```

---

### Task 4: Canonical column names

This is what removes `standardize_col_names` and the nine hardcoded year lists.

**Files:**
- Create: `pipeline/column_map.py`
- Test: `tests/test_column_map.py`

**Interfaces:**
- Produces: `pipeline.column_map.canonical(raw_name: str) -> str | None`. Returns
  `None` for columns that are deliberately not loaded. Also
  `pipeline.column_map.canonical_frame(df) -> pandas.DataFrame` renaming and
  dropping in one pass.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_column_map.py
import pytest
from pipeline.column_map import canonical


@pytest.mark.parametrize("raw,expected", [
    # the year-stamped metric names, across editions
    ("np6017", "np"), ("np6024", "np"),
    ("nc9617", "nc"), ("nc9624", "nc"),
    ("h17", "h"), ("h24", "h"),
    ("hm17", "hm"), ("hm24", "hm"),
    ("np6019 cited9619", "np_cited"),
    ("np6024 cited9624", "np_cited"),
    # self-citations-excluded variants
    ("nc9624 (ns)", "nc_ns"),
    ("rank (ns)", "rank_ns"),
    ("np6024 cited9624 (ns)", "np_cited_ns"),
    # the version 7 retraction columns
    ("np6024_rw", "np_rw"),
    ("nc9624_to_rw", "nc_to_rw"),
    ("nc9624_rw", "nc_rw"),
    # the version 3-6 columns they replaced
    ("np6022_d", "np_d"),
    ("nc9622_d", "nc_d"),
    # stable names
    ("authfull", "authfull"), ("inst_name", "inst_name"), ("cntry", "cntry"),
    ("firstyr", "firstyr"), ("lastyr", "lastyr"), ("c", "c"), ("rank", "rank"),
    ("self%", "self_pct"),
    ("rank sm-subfield-1", "rank_subfield"),
    ("rank sm-subfield-1 (ns)", "rank_subfield_ns"),
    ("sm-subfield-1 count", "subfield_count"),
    # the 2017 rename
    ("npsf", "cpsf"), ("npsf (ns)", "cpsf_ns"),
    # the 2017 taxonomy, mapped onto the later scheme
    ("name1", "sm-subfield-1"), ("frac1", "sm-subfield-1-frac"),
    ("name22", "sm-field"), ("frac22", "sm-field-frac"),
])
def test_canonical_names(raw, expected):
    assert canonical(raw) == expected


def test_unmapped_columns_are_dropped_not_guessed():
    # 2017's numeric taxonomy codes have no equivalent in later editions
    assert canonical("sm-1") is None
    assert canonical("sm22") is None


def test_nc_to_rw_is_not_confused_with_nc_rw():
    assert canonical("nc9624_to_rw") != canonical("nc9624_rw")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_column_map.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'pipeline'`

- [ ] **Step 3: Implement `pipeline/column_map.py`**

Order matters. `nc9624_to_rw` must be tested before `nc9624_rw`, and the
`cited` pattern before the bare `np` pattern, or the shorter pattern wins.

```python
"""Map each edition's year-stamped column names onto stable canonical names.

Every edition renames the same quantities: np6017 in 2017 is np6024 in 2024.
This is the sole reason standardize_col_names existed. Here the year is stripped
and lives in the row instead, via edition_id.
"""
import re

# Checked in order. The first match wins, so longer patterns come first.
PATTERNS = [
    (re.compile(r"^np\d{4} cited\d{4}$"), "np_cited"),
    (re.compile(r"^nc\d{4}_to_rw$"), "nc_to_rw"),
    (re.compile(r"^nc\d{4}_rw$"), "nc_rw"),
    (re.compile(r"^np\d{4}_rw$"), "np_rw"),
    (re.compile(r"^nc\d{4}_d$"), "nc_d"),
    (re.compile(r"^np\d{4}_d$"), "np_d"),
    (re.compile(r"^np\d{4}$"), "np"),
    (re.compile(r"^nc\d{4}$"), "nc"),
    (re.compile(r"^hm\d{2}$"), "hm"),
    (re.compile(r"^h\d{2}$"), "h"),
]

LITERAL = {
    "self%": "self_pct",
    "rank sm-subfield-1": "rank_subfield",
    "sm-subfield-1 count": "subfield_count",
    # Renamed after the 2017 edition; both mean single+first authored papers.
    "npsf": "cpsf",
    # The 2017 edition's taxonomy, mapped onto every later edition's scheme.
    # name1/frac1 is the 176-subfield level, name22/frac22 the 22-field level;
    # Table-S3.xlsx sheets SM176 and SM22 are the code-to-name lookups.
    "name1": "sm-subfield-1",
    "frac1": "sm-subfield-1-frac",
    "name22": "sm-field",
    "frac22": "sm-field-frac",
}

# Present in the source but deliberately not loaded: 2017's numeric taxonomy
# codes, which have no equivalent in any later edition.
DROP = {"sm-1", "sm-2", "sm22", "name2", "frac2"}

PASS_THROUGH = {
    "authfull", "inst_name", "cntry", "firstyr", "lastyr", "rank", "c",
    "nps", "ncs", "cpsf", "ncsf", "npsfl", "ncsfl", "npciting", "cprat",
    "sm-subfield-1", "sm-subfield-1-frac", "sm-subfield-2",
    "sm-subfield-2-frac", "sm-field", "sm-field-frac",
}


def canonical(raw_name):
    name = str(raw_name).strip()

    suffix = ""
    if name.endswith(" (ns)"):
        name, suffix = name[:-5].strip(), "_ns"

    if name in DROP:
        return None
    if name in LITERAL:
        return LITERAL[name] + suffix
    if name in PASS_THROUGH:
        return name + suffix
    for pattern, replacement in PATTERNS:
        if pattern.match(name):
            return replacement + suffix
    return None


def canonical_frame(df):
    renames, drops = {}, []
    for column in df.columns:
        mapped = canonical(column)
        if mapped is None:
            drops.append(column)
        else:
            renames[column] = mapped
    return df.drop(columns=drops).rename(columns=renames)
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `pytest tests/test_column_map.py -v`
Expected: all PASS

- [ ] **Step 5: Verify the mapping covers every real column in every edition**

This is the step that catches a column nobody thought about. It must print
nothing for all 15 tables.

```bash
python - <<'PY'
import glob, pandas as pd
from pipeline.column_map import canonical
for path in sorted(glob.glob("data_clean/version-*/*.pkl")):
    if "LogTransform" in path:
        continue
    df = pd.read_pickle(path)
    unmapped = [c for c in df.columns if canonical(c) is None]
    unexpected = [c for c in unmapped
                  if c not in {"sm-1", "sm-2", "sm22", "name2", "frac2"}]
    if unexpected:
        print(path.split("/")[-1], "UNMAPPED:", unexpected)
PY
```
Expected: no output. Any line printed is a column the map does not handle; add it
to `LITERAL`, `PASS_THROUGH` or `DROP` with a comment saying which editions carry
it, and add a case to the test.

- [ ] **Step 6: Verify the 2017 taxonomy assumption before relying on it**

The mapping of `name1` to `sm-subfield-1` assumes the two use the same
vocabulary. Check it rather than trust it.

```bash
python - <<'PY'
import glob, pandas as pd
old = pd.read_pickle(glob.glob("data_clean/version-1/Table-S1-career-2017.pkl")[0])
new = pd.read_pickle([p for p in glob.glob(
    "data_clean/version-8/*career*.pkl") if "LogTransform" not in p][0])
a, b = set(old["name22"].dropna()), set(new["sm-field"].dropna())
print(f"2017 name22 values: {len(a)},  2024 sm-field values: {len(b)}")
print(f"shared: {len(a & b)}")
print("only in 2017:", sorted(a - b)[:10])
print("only in 2024:", sorted(b - a)[:10])
PY
```
Expected: a large shared vocabulary. If the overlap is small, the assumption is
wrong: change `LITERAL` to drop `name1`/`name22` instead, mark 2017 field data
unavailable in `editions.columns_present`, and record the decision in the spec's
open questions.

- [ ] **Step 7: Commit**

```bash
git add pipeline/column_map.py tests/test_column_map.py
git commit -m "feat: canonical column names, replacing standardize_col_names"
```

---

### Task 5: Author identity resolution

**Files:**
- Create: `pipeline/identity.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Produces:
  - `pipeline.identity.normalize(name: str) -> str`
  - `pipeline.identity.block_key(name: str) -> tuple[str, str]` returning
    `(surname, first_initial)`
  - `pipeline.identity.resolve(observations) -> list[Resolution]` where
    `observations` is an iterable of dicts with keys `edition_id`, `authfull`,
    `firstyr`, `inst_name`, `cntry`, and `Resolution` is a dataclass with fields
    `author_id`, `edition_id`, `authfull`, `method`, `is_confident`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_identity.py
from pipeline.identity import normalize, block_key, resolve


def test_block_key_is_stable_across_given_name_expansion():
    # The 2023 -> 2024 break: Scopus expanded abbreviated preferred names.
    assert block_key("Severinghaus, J. W.") == block_key("Severinghaus, John Wendell")
    assert block_key("Cotran, Ramzi") == block_key("Cotran, Ramzi S.")
    assert block_key("Dahmen, U.") == block_key("Dahmen, Ulrich")


def test_block_key_separates_different_people():
    assert block_key("Dahmen, Karin A.") != block_key("Dahmen, Ulrich")


def test_normalize_folds_accents():
    assert normalize("Grätzel, Michael") == normalize("Gratzel, Michael")


def test_same_person_across_editions_gets_one_id():
    observations = [
        {"edition_id": "career_2023", "authfull": "Severinghaus, J. W.",
         "firstyr": 1958, "inst_name": "UCSF", "cntry": "usa"},
        {"edition_id": "career_2024", "authfull": "Severinghaus, John Wendell",
         "firstyr": 1958, "inst_name": "UCSF", "cntry": "usa"},
    ]
    resolutions = resolve(observations)
    assert len({r.author_id for r in resolutions}) == 1
    assert all(r.is_confident for r in resolutions)


def test_two_people_in_one_edition_are_never_merged():
    # Each edition lists each author exactly once, so two rows in the same
    # edition are two different humans by construction.
    observations = [
        {"edition_id": "career_2021", "authfull": "Abraham, Edward",
         "firstyr": 1975, "inst_name": "University of Miami", "cntry": "usa"},
        {"edition_id": "career_2021", "authfull": "Abraham, Edward",
         "firstyr": 1975, "inst_name": "Dragonfly Data Science", "cntry": "nzl"},
    ]
    resolutions = resolve(observations)
    assert len({r.author_id for r in resolutions}) == 2
    assert not any(r.is_confident for r in resolutions)


def test_nothing_is_dropped():
    observations = [
        {"edition_id": "career_2021", "authfull": "Abe, Hiroshi",
         "firstyr": 1990, "inst_name": "Fukuoka University", "cntry": "jpn"},
        {"edition_id": "career_2021", "authfull": "Abe, Hiroshi",
         "firstyr": 1985, "inst_name": "Riken", "cntry": "jpn"},
        {"edition_id": "career_2022", "authfull": "Abe, Hiroshi",
         "firstyr": 1990, "inst_name": "Fukuoka University", "cntry": "jpn"},
    ]
    assert len(resolve(observations)) == 3


def test_author_ids_are_deterministic():
    observations = [{"edition_id": "career_2024", "authfull": "Wang, Zhong Lin",
                     "firstyr": 1986, "inst_name": "Georgia Tech", "cntry": "usa"}]
    assert resolve(observations)[0].author_id == resolve(observations)[0].author_id
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_identity.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'pipeline.identity'`

- [ ] **Step 3: Implement `pipeline/identity.py`**

```python
"""Resolve author identity across editions.

The source data carries no author identifier, only a formatted name string that
is the Scopus profile's preferred name at calculation time. Between the 2023 and
2024 editions 90,755 of those strings changed, because Scopus expanded
abbreviated given names, so exact-name matching links only 57.7 percent of
authors across that boundary against a 79-85 percent baseline elsewhere.

Blocking on surname plus first initial plus firstyr restores it to 85.2 percent.
firstyr is the right third component because it is a property of a career rather
than of current circumstances: it is identical for 94-97 percent of
exactly-matched names, where institution manages only 69-84 percent. Country was
measured and rejected, because researchers relocate and it costs matches.

Two rules are absolute. Two rows in the same edition are two different people and
must never merge. Nothing is ever dropped; what does not resolve becomes a
separate author flagged ambiguous.
"""
import hashlib
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Resolution:
    author_id: str
    edition_id: str
    authfull: str
    method: str
    is_confident: bool


def normalize(name):
    decomposed = unicodedata.normalize("NFKD", str(name))
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).strip()


def block_key(name):
    """(surname, first initial). Stable when a given name is expanded."""
    text = normalize(name)
    surname, _, given = text.partition(" ")
    given_parts = given.split()
    return surname, (given_parts[0][0] if given_parts else "")


def _author_id(surname, initial, firstyr, discriminator):
    raw = f"{surname}|{initial}|{firstyr}|{discriminator}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def resolve(observations):
    blocks = {}
    for obs in observations:
        surname, initial = block_key(obs["authfull"])
        blocks.setdefault((surname, initial), []).append(obs)

    resolutions = []
    for (surname, initial), members in blocks.items():
        by_firstyr = {}
        for obs in members:
            by_firstyr.setdefault(obs.get("firstyr"), []).append(obs)

        for firstyr, group in by_firstyr.items():
            editions = [o["edition_id"] for o in group]
            # One row per edition means one person. More than one row in any
            # single edition means the firstyr did not disambiguate them.
            ambiguous = len(editions) != len(set(editions))

            if not ambiguous:
                author_id = _author_id(surname, initial, firstyr, "")
                for obs in group:
                    resolutions.append(Resolution(
                        author_id=author_id,
                        edition_id=obs["edition_id"],
                        authfull=obs["authfull"],
                        method="surname_initial_firstyr",
                        is_confident=True,
                    ))
                continue

            # Fall back to institution as a tiebreaker, and keep every row as its
            # own author when even that fails. Never merge, never drop.
            for obs in group:
                discriminator = normalize(obs.get("inst_name") or "")
                resolutions.append(Resolution(
                    author_id=_author_id(surname, initial, firstyr, discriminator),
                    edition_id=obs["edition_id"],
                    authfull=obs["authfull"],
                    method="surname_initial_firstyr_institution",
                    is_confident=False,
                ))

    return resolutions
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `pytest tests/test_identity.py -v`
Expected: all six PASS

- [ ] **Step 5: Reproduce the measured linkage rate on real data**

This is a regression test for the design's central claim. If this number moves,
something is wrong.

```bash
python - <<'PY'
import glob, pandas as pd
from pipeline.identity import block_key

def load(v):
    p = [x for x in glob.glob(f"data_clean/version-{v}/*career*.pkl")
         if "LogTransform" not in x][0]
    return pd.read_pickle(p)[["authfull", "firstyr"]]

a, b = load(7), load(8)
for df in (a, b):
    df["key"] = [block_key(n) + (y,) for n, y in zip(df.authfull, df.firstyr)]

ua = a[~a.key.duplicated(keep=False)]
ub = b[~b.key.duplicated(keep=False)]
linked = len(ua.merge(ub, on="key"))
exact = len(set(a.authfull) & set(b.authfull))
print(f"exact name match : {exact:,}")
print(f"block key match  : {linked:,}  ({100*linked/a.authfull.nunique():.1f}% of 2023)")
PY
```
Expected: exact around 122,897, block key around 181,334, which is roughly 85
percent of 2023. If the block-key number is materially below 180,000,
`block_key` or `normalize` has a bug; do not proceed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/identity.py tests/test_identity.py
git commit -m "feat: author identity resolution across editions"
```

---

### Task 6: Load Postgres and export Parquet

**Files:**
- Create: `pipeline/build_relational.py`
- Test: `tests/test_build_relational.py`

**Interfaces:**
- Consumes: `pipeline.column_map.canonical_frame`, `pipeline.identity.resolve`,
  `db.connection.connect`.
- Produces: a populated database, and Parquet files under `data_parquet/`, one per
  table, named `<table>.parquet`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build_relational.py
import os
import psycopg
import pytest
from db.migrate import apply_all
from pipeline.build_relational import load_edition

DSN = os.environ["DATABASE_URL"]


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as c:
        c.execute("drop schema public cascade; create schema public;")
        c.commit()
        apply_all(c, "db/migrations")
        yield c


def test_loading_one_edition_preserves_every_row(conn):
    rows = load_edition(conn, "data_clean/version-8", kind="career")
    loaded = conn.execute("select count(*) from career_metrics").fetchone()[0]
    assert loaded == rows == 230333


def test_no_author_row_is_dropped_on_name_collision(conn):
    load_edition(conn, "data_clean/version-5", kind="career")
    loaded = conn.execute("select count(*) from career_metrics").fetchone()[0]
    # The old create_composite_dict kept selected_data[0] and lost ~3,232 rows.
    assert loaded == 194983


def test_year_stamped_columns_are_gone(conn):
    load_edition(conn, "data_clean/version-8", kind="career")
    columns = {r[0] for r in conn.execute(
        "select column_name from information_schema.columns "
        "where table_name = 'career_metrics'").fetchall()}
    assert "np" in columns and "nc" in columns and "h" in columns
    assert not any(c.startswith("np60") or c.startswith("nc96") for c in columns)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `DATABASE_URL=... pytest tests/test_build_relational.py -v`
Expected: FAIL, cannot import `load_edition`

- [ ] **Step 3: Implement `pipeline/build_relational.py`**

Write it in this order: read the cleaned pickle, apply `canonical_frame`, upsert
the dimension rows (`countries`, `institutions`, `fields`, `subfields`), resolve
identity for that edition's observations together with every edition already
loaded, insert `authors` and `author_name_observations`, then bulk-insert the
fact rows with `psycopg`'s `copy` for speed. Compute `metric_maxima` per edition
and metric as the final step of each edition. Export every table with
`COPY ... TO STDOUT (FORMAT csv)` into pandas and `to_parquet`.

Identity resolution must run over all editions at once, not per edition, because
a block spans editions. Load all cleaned frames first, resolve once, then insert.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `DATABASE_URL=... pytest tests/test_build_relational.py -v`
Expected: PASS. The row-count assertions are the guard against the
`selected_data[0]` regression.

- [ ] **Step 5: Run the full build and reconcile every edition**

```bash
python pipeline/build_relational.py data_clean
psql $DATABASE_URL -c "
  select e.data_year, e.kind, count(*)
  from career_metrics m join editions e using (edition_id)
  group by 1,2 union all
  select e.data_year, e.kind, count(*)
  from singleyr_metrics m join editions e using (edition_id)
  group by 1,2 order by 2,1;"
```
Expected total across both tables: 2,730,673. Career 2017 must be 105,026 and
career 2024 must be 230,333. Any edition short by a few thousand rows means
identity resolution merged rows it should not have.

- [ ] **Step 6: Commit**

```bash
git add pipeline/build_relational.py tests/test_build_relational.py
git commit -m "feat: load all eight editions into Postgres, export Parquet"
```

---

### Task 7: Group aggregates as a materialized view

**Files:**
- Create: `db/migrations/002_group_metrics.sql`
- Test: `tests/test_group_metrics.py`

**Interfaces:**
- Produces: materialized view `group_metrics(edition_id, group_kind, group_value,
  metric, min, q1, median, q3, max, n)` where `group_kind` is one of `cntry`,
  `sm-field`, `inst_name`, matching the argument `get_es_aggregate` already takes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_group_metrics.py
import os, psycopg

DSN = os.environ["DATABASE_URL"]


def test_group_metrics_has_all_three_groupings():
    with psycopg.connect(DSN) as conn:
        kinds = {r[0] for r in conn.execute(
            "select distinct group_kind from group_metrics").fetchall()}
        assert kinds == {"cntry", "sm-field", "inst_name"}


def test_quartiles_are_ordered():
    with psycopg.connect(DSN) as conn:
        bad = conn.execute(
            "select count(*) from group_metrics "
            "where not (min <= q1 and q1 <= median "
            "and median <= q3 and q3 <= max)").fetchone()[0]
        assert bad == 0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `DATABASE_URL=... pytest tests/test_group_metrics.py -v`
Expected: FAIL, `relation "group_metrics" does not exist`

- [ ] **Step 3: Write `db/migrations/002_group_metrics.sql`**

Use `percentile_cont(array[0.25, 0.5, 0.75])` over each metric, grouped by
edition and by each of country, field and institution in turn, unioned together
with a literal `group_kind`. Index on `(edition_id, group_kind, group_value)`.

- [ ] **Step 4: Apply and run the tests**

Run: `python db/migrate.py && DATABASE_URL=... pytest tests/test_group_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db/migrations/002_group_metrics.sql tests/test_group_metrics.py
git commit -m "feat: group aggregates as a materialized view"
```

---

### Task 8: Slim search index

**Files:**
- Create: `pipeline/build_search_index.py`
- Test: `tests/test_search_index.py`

**Interfaces:**
- Produces: `pipeline.build_search_index.build(es, conn, alias="authors") -> str`
  returning the concrete index name it created, having pointed `alias` at it and
  removed the previous one.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search_index.py
import os
from elasticsearch import Elasticsearch
import psycopg
from pipeline.build_search_index import build

ES = Elasticsearch([os.environ["ELASTICSEARCH_URL"]])


def test_documents_carry_no_blob():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        build(ES, conn, alias="authors_test")
    hit = ES.search(index="authors_test", size=1)["hits"]["hits"][0]["_source"]
    assert "data" not in hit
    assert set(hit) == {"author_id", "authfull", "name_normalized",
                        "inst_name", "cntry", "sm_field", "years_present"}


def test_alias_swap_leaves_exactly_one_index():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        first = build(ES, conn, alias="authors_test")
        second = build(ES, conn, alias="authors_test")
    assert first != second
    assert set(ES.indices.get_alias(name="authors_test")) == {second}
    assert not ES.indices.exists(index=first)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_search_index.py -v`
Expected: FAIL, cannot import `build`

- [ ] **Step 3: Implement `pipeline/build_search_index.py`**

Create `authors_<utc timestamp>`, bulk-index one document per author from
Postgres with exactly the seven fields above, refresh, atomically repoint the
alias with a single `indices.update_aliases` call containing both the remove and
the add, then delete the old index. The atomic swap is the point: the dashboard
must never see a window with no index, which is what deleting before rebuilding
causes today.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `pytest tests/test_search_index.py -v`
Expected: PASS

- [ ] **Step 5: Build the real index and compare its size**

```bash
python pipeline/build_search_index.py
curl -s 'localhost:9201/_cat/indices?v&bytes=mb'
```
Expected: the authors index is tens of megabytes, against roughly 700 MB for the
old `career` plus `singleyr` indices recorded in `bench/README.md`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/build_search_index.py tests/test_search_index.py
git commit -m "feat: blob-free search index with atomic alias swap"
```

---

### Task 9: Reimplement the four seam functions

The whole dashboard reaches Elasticsearch through four functions. Replacing their
bodies while keeping their signatures migrates the entire app without touching
`single_author_layout.py`, `group_vs_group_layout.py`, `author_vs_author_layout.py`,
`author_vs_group_layout.py`, `auth_find.py`, `callback_templates.py`, `pages/home.py`
or `pages/test.py`.

**Files:**
- Modify: `citations_lib/utils.py:24-29`, `:88-99`, `:111-123`, `:125-156`, `:158-173`
- Test: `tests/test_queries.py`

**Interfaces:**
- Consumes: `db.connection.connect`, the `authors` alias from Task 8.
- Produces: unchanged public signatures, listed in Global Constraints.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_queries.py
from citations_lib.utils import get_es_results, es_result_pick, get_es_aggregate


def test_typeahead_returns_names_for_a_prefix():
    result = get_es_results("ioannidis", ["career", "singleyr"], "authfull")
    names = es_result_pick(result, "authfull")
    assert any("Ioannidis" in n for n in names)


def test_typeahead_is_still_typo_tolerant():
    result = get_es_results("ioanidis", ["career", "singleyr"], "authfull")
    assert es_result_pick(result, "authfull")


def test_author_data_shape_matches_the_old_blob():
    result = get_es_results("Ioannidis, John P.A.", "career", "authfull")
    data = es_result_pick(result, "data", None)
    assert isinstance(data, dict)
    # Keys were "<prefix>_<year>" and "<prefix>_<year>_log"; layouts split on "_".
    assert any(k.startswith("career_") for k in data)
    assert any(k.endswith("_log") for k in data)


def test_new_editions_are_present():
    result = get_es_results("Ioannidis, John P.A.", "career", "authfull")
    data = es_result_pick(result, "data", None)
    for year in ("2022", "2023", "2024"):
        assert f"career_{year}" in data


def test_group_aggregate_still_returns_summary_vectors():
    data = get_es_aggregate("cntry", "United States", "career")
    assert data
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_queries.py -v`
Expected: FAIL. `test_new_editions_are_present` fails even against the old code,
which is the point: it encodes the goal.

- [ ] **Step 3: Rewrite the four functions**

`get_es_results` keeps its `multi_match` with `fuzziness: "auto"` against the
`authors` alias, but adds `"_source"` filtering so the typeahead ships names
rather than documents. When `field == "data"`, `es_result_pick` queries Postgres
for that author's rows across every edition and assembles the same nested dict
the blob used to hold, keyed `career_2021` and `career_2021_log`, applying the
log transform from `metric_maxima` at read time. `get_es_aggregate` becomes a
single select against `group_metrics`. `base64_decode_and_decompress` is kept as
a thin shim that raises a clear error, since nothing should call it any more.

Do not change any signature. Do not edit any other file.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `pytest tests/test_queries.py -v`
Expected: all five PASS

- [ ] **Step 5: Confirm no other file changed**

Run: `git diff --name-only`
Expected: exactly `citations_lib/utils.py` and `tests/test_queries.py`. If any
layout module appears, the seam was broken; revert and reconsider.

- [ ] **Step 6: Run the app and click through every page**

```bash
make up && python app.py
```
Open `http://localhost:8050`. Check the author search, single author view, author
versus author, author versus group, group versus group, and the world map. The
year selectors must now offer 2022, 2023 and 2024.

- [ ] **Step 7: Commit**

```bash
git add citations_lib/utils.py tests/test_queries.py
git commit -m "feat: serve dashboard from Postgres, keep Elasticsearch for search"
```

---

### Task 10: Latency gate

**Files:**
- Modify: `bench/latency.py`, `bench/README.md`
- Create: `bench/after.json`

- [ ] **Step 1: Measure the new stack**

```bash
python bench/latency.py --mode current --out bench/after.json
python - <<'PY'
import json
before, after = json.load(open("bench/baseline.json")), json.load(open("bench/after.json"))
for key in ("typeahead_p50_ms", "typeahead_p95_ms", "fetch_p50_ms", "fetch_p95_ms"):
    delta = after[key] - before[key]
    print(f"{key:22s} {before[key]:8.2f} -> {after[key]:8.2f}  ({delta:+.2f} ms)")
PY
```

- [ ] **Step 2: Apply the gate**

The spec's acceptance criterion is match or beat, on both phases, at p50 and p95.
If typeahead regressed, check that `_source` filtering is actually in the query.
If the author fetch regressed, the Postgres round trip is the cost: add a
covering index on `career_metrics (author_id, edition_id)`, and only if that is
insufficient, a narrow denormalized table. Do not reintroduce blobs.

- [ ] **Step 3: Record both numbers in `bench/README.md` and commit**

```bash
git add bench/
git commit -m "test: post-migration latency, meets the acceptance gate"
```

---

### Task 11: Production deployment on dokku

**Files:**
- Modify: `README.md`, `requirements.txt`, `Procfile`
- Create: `deploy/dokku.md`

- [ ] **Step 1: Add the new dependencies**

```bash
printf 'psycopg[binary]==3.2.3\npyarrow==17.0.0\n' >> requirements.txt
```

- [ ] **Step 2: Write `deploy/dokku.md`**

Replace the README's Elasticsearch-only setup with both services. The
Elasticsearch service stays; a Postgres service joins it.

```bash
sudo dokku plugin:install https://github.com/dokku/dokku-postgres.git postgres
dokku postgres:create twopct
dokku postgres:link twopct twopercenters      # exports DATABASE_URL

dokku elasticsearch:create citedb             # unchanged from the current setup
dokku elasticsearch:link citedb twopercenters # exports ELASTICSEARCH_URL

dokku ps:scale twopercenters web=1
git push dokku main:master
dokku run twopercenters python db/migrate.py
```

The data build runs off the server, because it needs the 1.2 GB of source
spreadsheets and several minutes of CPU. Build locally, then load the dump:

```bash
pg_dump $LOCAL_DATABASE_URL | dokku postgres:connect twopct
dokku run twopercenters python pipeline/build_search_index.py
```

- [ ] **Step 3: Update `README.md`**

Remove the instructions that describe indexing blobs with `elasticSearchIdx.py`
and point at `deploy/dokku.md` and the Makefile instead. Keep the manifest and
`fetch_sources.py` description: reproducing the data from source is the point.

- [ ] **Step 4: Deploy and verify**

```bash
dokku ps:report twopercenters
curl -sI https://<host>/ | head -1
```
Expected: HTTP 200, and the deployed dashboard offers years through 2024.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt deploy/dokku.md README.md
git commit -m "docs: dokku deployment with Postgres alongside Elasticsearch"
```

---

## What this plan deliberately leaves out

`elasticSearchIdx.py`, `prep_for_elasticsearch.ipynb` and
`code_test_preproc/02_data_preproc_for_speed.ipynb` are superseded by Tasks 6, 7
and 8 but are not deleted here. Leave them until the deployment is confirmed
working, then remove them in a separate commit. Deleting them in the same change
that replaces them makes the diff hard to review and the rollback hard to find.

The Kumo Relational demo, the OpenAlex enrichment, and the entity resolution
evaluation are plan 2. They consume `data_parquet/` from Task 6 and depend on
nothing else here.
