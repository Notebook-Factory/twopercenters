# Kumo Relational Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the relational core built in plan 1 into a working KumoRFM demo: a materialized graph, five predictive queries, an OpenAlex co-authorship enrichment, and a natural-language query box in the dashboard.

**Architecture:** A new top-level `kumo/` package in the **existing virtual environment**. `kumoai` was verified to install and import cleanly on the dashboard's exact pinned stack, Python 3.10 with pandas 1.5.2 and numpy 1.21.5, with `pip check` clean, so no version upgrade is needed anywhere. `kumo/` reads the Parquet tables already exported by plan 1, declares a graph schema, and drives KumoRFM through `kumoai.experimental.rfm`. The dashboard imports it directly.

Keeping the prediction work in a separate module rather than a separate process is a deliberate simplification, but it is bounded: the materialized graph is roughly 1.4 GB of resident pandas, so whether the prediction page ships to the dokku host is a memory question decided in Task 8, not a dependency question.

**Tech Stack:** `kumo-rfm-mcp==0.3.1`, `kumoai`, pandas 1.5.2, numpy 1.21.5, pyarrow 17, Dash 2.15, Postgres 16. All existing versions, unchanged.

**Spec:** `docs/superpowers/specs/2026-09-13-twopercenters-relational-redesign-design.md`

## Global Constraints

- **One environment, no version changes.** The Kumo dependencies go into the existing `requirements.txt` and the existing `.venv`. `pandas==1.5.2`, `numpy==1.21.5`, `pyarrow==17.0.0` and `runtime.txt`'s `python-3.10.14` all stay exactly as they are: `kumoai` was verified against them. If any task finds itself wanting to bump one of those pins, stop and report rather than bumping it, because the dashboard's 118 tests and the verified pickle reproduction both depend on them.
- **Kumo is an optional import.** `import kumoai` must never happen at dashboard import time. The prediction page imports it lazily, inside the callback, so that a deployment without a Kumo key or without the memory for a graph still serves every other page.
- **`KUMO_API_KEY` comes from the environment only.** Never write it to a file, never commit it, never echo it in logs or reports. `kumo-rfm-mcp` falls back to an OAuth2 browser flow if it is unset.
- **A `predict` or `evaluate` call accepts at most 1000 entities.** Every demo runs on a sample; every full-table pass is an explicit batched job with a progress log and resumability.
- **PQL is not SQL.** No arithmetic. No `JOIN`, `SELECT`, `GROUP BY`, or subqueries. `LIST_DISTINCT` applies only to foreign key columns and requires `RANK TOP k` with 1 <= k <= 20. Do not invent syntax: the authoritative grammar is the MCP resource `kumo://docs/predictive-query`, also on disk at `<site-packages>/kumo_rfm_mcp/resources/predictive-query.md`.
- **Static imputation entities are fact rows.** The target column must live in the entity's own table, so imputation over `career_metrics` uses `FOR EACH career_metrics.metric_id`, with `anchor_time='entity'` to prevent temporal leakage.
- **Temporal entity filters are backward looking:** `start < 0`, `end <= 0`, `end > start`. Target windows are non-negative with `end > start`. Units: `seconds`, `minutes`, `hours`, `days`, `weeks`, `months`; default `days`.
- **Measured, not asserted.** Every claim about accuracy comes from `evaluate` output pasted into the task report. No number reaches a document without the call that produced it.
- **`data_parquet/`, `data_raw/` and `data_clean/` stay gitignored.** Add `kumo/out/` as well; prediction outputs are regenerable.

---

### Task 1: The Kumo package, its environment, and the graph memory budget

The spec flags local memory as an open risk: `materialize_graph` reads every table with `pd.read_parquet` into a `LocalTable`, so the whole graph sits in the host process. Measured totals for the plan-1 export are 3,664 MB in pandas across ten tables, of which `career_metrics` is 1,281 MB, `singleyr_metrics` 1,218 MB and `author_name_observations` 842 MB. This task decides what actually goes into the core graph and proves the decision by measurement.

**Files:**
- Create: `kumo/__init__.py`
- Modify: `requirements.txt`
- Create: `kumo/tables.py`
- Create: `kumo/measure_memory.py`
- Modify: `.gitignore`
- Modify: `Makefile`
- Test: `kumo/tests/test_tables.py`

**Interfaces:**
- Consumes: the Parquet files in `data_parquet/` produced by `pipeline/build_relational.py`.
- Produces:
  - `kumo.tables.CORE_TABLES: dict[str, TableSpec]`: the tables in the core graph.
  - `kumo.tables.TableSpec`: a dataclass with fields `name: str`, `path: str`, `primary_key: str | None`, `time_column: str | None`, `drop_columns: list[str]`, `stypes: dict[str, str]`.
  - `kumo.tables.load(name: str) -> pandas.DataFrame`: reads the Parquet file and applies `drop_columns`.

- [ ] **Step 1: Write the failing test**

```python
# kumo/tests/test_tables.py
import pytest
from kumo import tables


def test_core_tables_cover_the_five_queries():
    """career_metrics and its dimensions must be present; the demo queries
    all run over the career editions."""
    assert "career_metrics" in tables.CORE_TABLES
    assert "authors" in tables.CORE_TABLES
    assert "institutions" in tables.CORE_TABLES
    assert "editions" in tables.CORE_TABLES


def test_career_metrics_has_a_primary_key_and_a_time_column():
    """Static imputation needs the fact row as an entity, which needs a
    primary key; temporal queries need the time column."""
    spec = tables.CORE_TABLES["career_metrics"]
    assert spec.primary_key == "metric_id"
    assert spec.time_column == "observation_date"


def test_ns_columns_are_dropped_from_the_graph():
    """The _ns columns are non-self-citation restatements of the main
    metrics. They add width and noise without adding a question."""
    spec = tables.CORE_TABLES["career_metrics"]
    assert all(c.endswith("_ns") for c in spec.drop_columns)
    assert len(spec.drop_columns) == 15


def test_retraction_columns_survive():
    """nc_rw is the centrepiece target; dropping it would be silent."""
    spec = tables.CORE_TABLES["career_metrics"]
    for col in ("np_rw", "nc_rw", "nc_to_rw"):
        assert col not in spec.drop_columns


def test_load_applies_the_drops():
    df = tables.load("career_metrics")
    assert not [c for c in df.columns if c.endswith("_ns")]
    assert "nc_rw" in df.columns
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest kumo/tests/test_tables.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kumo.tables'`

- [ ] **Step 3: Add Kumo to the existing environment**

Append one line to `requirements.txt`, leaving every existing pin untouched:

```
kumo-rfm-mcp==0.3.1
```

```bash
.venv/bin/pip install -r requirements.txt
```

Then confirm the thing that makes this safe, which was verified before the plan was written but must be re-confirmed in this environment:

```bash
.venv/bin/pip check
.venv/bin/python -c "
import pandas, numpy, pyarrow
print(pandas.__version__, numpy.__version__, pyarrow.__version__)
from kumoai.experimental import rfm
print('rfm ok')
"
```

Expected: `pip check` reports no broken requirements, and the versions print `1.5.2 1.21.5 17.0.0` unchanged. Installing adds about 110 packages and 400 MB of site-packages, which is the real cost of this choice and is worth noting in the report.

**If pip upgrades pandas, numpy or pyarrow, stop and report it.** That would mean the resolver behaves differently here than in verification, and the dashboard's 118 tests plus the verified pickle reproduction both rest on those pins.

- [ ] **Step 4: Write `kumo/tables.py`**

```python
"""The tables that make up the KumoRFM graph, and what each column means to it.

Only the career editions are in the core graph. singleyr_metrics is a second
1,218 MB table that answers none of the five demo queries -- every one of them
is about career trajectories -- and the graph materializes in local memory, so
it is left out deliberately rather than forgotten. Task 6 revisits this if
co-authorship makes it useful.

author_name_observations (2,730,673 rows, 842 MB) is likewise out of the core
graph. It is the name history, which matters only to the entity resolution
question in Task 7, where it is added as a separate graph.
"""
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PARQUET_DIR = Path(__file__).resolve().parent.parent / "data_parquet"

# The non-self-citation restatements. Every one of these is the same metric
# recomputed with self-citations removed, so they correlate almost perfectly
# with their bare counterparts. Keeping them costs 185 MB and gives the model
# fifteen near-duplicate columns to spread attention over.
NS_COLUMNS = [
    "rank_ns", "c_ns", "h_ns", "hm_ns", "nc_ns", "nps_ns", "ncs_ns",
    "cpsf_ns", "ncsf_ns", "npsfl_ns", "ncsfl_ns", "npciting_ns",
    "cprat_ns", "np_cited_ns", "rank_subfield_ns",
]


@dataclass(frozen=True)
class TableSpec:
    name: str
    path: str
    primary_key: str | None = None
    time_column: str | None = None
    drop_columns: list[str] = field(default_factory=list)
    stypes: dict[str, str] = field(default_factory=dict)


CORE_TABLES: dict[str, TableSpec] = {
    "career_metrics": TableSpec(
        name="career_metrics",
        path=str(PARQUET_DIR / "career_metrics.parquet"),
        primary_key="metric_id",
        time_column="observation_date",
        drop_columns=list(NS_COLUMNS),
        stypes={
            "metric_id": "ID",
            "author_id": "ID",
            "edition_id": "ID",
            "institution_id": "ID",
            "field_id": "ID",
            "subfield_1_id": "ID",
            "subfield_2_id": "ID",
            "country_code": "ID",
            "observation_date": "timestamp",
            # firstyr and lastyr are years, not counts. They are numerical,
            # but their low cardinality makes Kumo's heuristic guess
            # "categorical", which would turn a regression into a
            # 60-way classification. Pinned deliberately.
            "firstyr": "numerical",
            "lastyr": "numerical",
            "rank": "numerical",
            "rank_subfield": "numerical",
            "subfield_count": "numerical",
            "np_rw": "numerical",
            "nc_rw": "numerical",
            "nc_to_rw": "numerical",
        },
    ),
    "authors": TableSpec(
        name="authors",
        path=str(PARQUET_DIR / "authors.parquet"),
        primary_key="author_id",
        stypes={
            "author_id": "ID",
            "authfull_display": "text",
            "name_normalized": "text",
            "surname": "categorical",
            "first_initial": "categorical",
            "firstyr": "numerical",
            "collision_group_size": "numerical",
            "is_ambiguous": "categorical",
            "first_data_year": "numerical",
            "last_data_year": "numerical",
        },
    ),
    "institutions": TableSpec(
        name="institutions",
        path=str(PARQUET_DIR / "institutions.parquet"),
        primary_key="institution_id",
        stypes={
            "institution_id": "ID",
            # 66,079 distinct names is too high a cardinality to encode as a
            # category, but as text it carries real signal ("University of",
            # "Hospital", country words).
            "inst_name": "text",
            "country_code": "categorical",
        },
    ),
    "editions": TableSpec(
        name="editions",
        path=str(PARQUET_DIR / "editions.parquet"),
        primary_key="edition_id",
        time_column="observation_date",
        # sha256 and source_filename are provenance for humans and pure noise
        # to the model: one distinct value per row, no generalization.
        drop_columns=["sha256", "source_filename", "columns_present"],
        stypes={
            "edition_id": "ID",
            "mendeley_version": "numerical",
            "data_year": "numerical",
            "kind": "categorical",
            "observation_date": "timestamp",
            "published_date": "timestamp",
        },
    ),
    "countries": TableSpec(
        name="countries",
        path=str(PARQUET_DIR / "countries.parquet"),
        primary_key="country_code",
        stypes={"country_code": "ID", "country_name": "categorical"},
    ),
    "fields": TableSpec(
        name="fields",
        path=str(PARQUET_DIR / "fields.parquet"),
        primary_key="field_id",
        stypes={"field_id": "ID", "field_name": "categorical"},
    ),
    "subfields": TableSpec(
        name="subfields",
        path=str(PARQUET_DIR / "subfields.parquet"),
        primary_key="subfield_id",
        stypes={"subfield_id": "ID", "subfield_name": "categorical"},
    ),
}


def load(name: str) -> pd.DataFrame:
    """Read one table's Parquet file and apply its declared drops."""
    spec = CORE_TABLES[name]
    df = pd.read_parquet(spec.path)
    drops = [c for c in spec.drop_columns if c in df.columns]
    return df.drop(columns=drops) if drops else df
```

Note: confirm the exact column names of `countries`, `fields` and `subfields`
before writing their `stypes` -- read them with
`.venv/bin/python -c "import pyarrow.parquet as pq; print(pq.ParquetFile('data_parquet/fields.parquet').schema_arrow.names)"`
and correct the dictionary to match. Do not assume `country_name`,
`field_name` and `subfield_id` are right.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest kumo/tests/test_tables.py -v`
Expected: PASS, 5 tests. If `test_ns_columns_are_dropped_from_the_graph` fails on the count, correct `NS_COLUMNS` against the real schema rather than the assertion.

- [ ] **Step 6: Write and run the memory measurement**

```python
# kumo/measure_memory.py
"""Report what the core graph costs in local memory.

materialize_graph reads every table with pd.read_parquet into a LocalTable, so
the graph lives in this process. This script is the evidence for what goes into
the core graph and what stays out.
"""
import pandas as pd

from kumo import tables


def main() -> None:
    total = 0.0
    print(f"{'table':26s} {'rows':>10s} {'cols':>5s} {'MB':>10s}")
    for name in tables.CORE_TABLES:
        df = tables.load(name)
        mb = df.memory_usage(deep=True).sum() / 1e6
        total += mb
        print(f"{name:26s} {len(df):10d} {df.shape[1]:5d} {mb:10.1f}")
        del df
    print(f"{'CORE GRAPH TOTAL':26s} {'':10s} {'':5s} {total:10.1f}")

    for excluded in ("singleyr_metrics", "author_name_observations"):
        df = pd.read_parquet(tables.PARQUET_DIR / f"{excluded}.parquet")
        mb = df.memory_usage(deep=True).sum() / 1e6
        print(f"{'(excluded) ' + excluded:26s} {len(df):10d} "
              f"{df.shape[1]:5d} {mb:10.1f}")
        del df


if __name__ == "__main__":
    main()
```

Run: `.venv/bin/python -m kumo.measure_memory`

Expected: the core graph total lands near 1,430 MB (career_metrics slim at roughly 1,096 MB, authors 307 MB, institutions 15 MB, dimensions negligible), against 3,664 MB for all ten tables. **Paste the real table into the task report.** If the core total exceeds 2,500 MB, stop and report it rather than proceeding: the graph schema in Task 2 would then need narrowing first.

- [ ] **Step 7: Wire it into the build and ignore the outputs**

Add to `.gitignore`:

```
kumo/out/
```

Add to the `Makefile`:

```makefile
kumo-memory:
	.venv/bin/python -m kumo.measure_memory
```

- [ ] **Step 8: Commit**

```bash
git add kumo/ .gitignore Makefile requirements.txt
git commit -m "kumo: the graph's tables and a measured memory budget"
```

---

### Task 2: The graph schema, its links, and a validation that catches a broken one

Kumo reads foreign keys as edges, and the spec is blunt about the consequence of getting this wrong: "Make sure that tables are correctly linked before proceeding." A missing link silently turns the graph into disconnected tables and every prediction degrades to single-table imputation without erroring.

**Files:**
- Create: `kumo/graph.py`
- Test: `kumo/tests/test_graph.py`

**Interfaces:**
- Consumes: `kumo.tables.CORE_TABLES`, `kumo.tables.load`.
- Produces:
  - `kumo.graph.LINKS: list[Link]` where `Link` is a dataclass with `source_table: str`, `foreign_key: str`, `destination_table: str`.
  - `kumo.graph.build_metadata() -> dict`: the payload for the MCP `update_graph_metadata` tool.
  - `kumo.graph.validate_links() -> list[str]`: returns a list of human-readable problems; empty means valid.

- [ ] **Step 1: Write the failing test**

```python
# kumo/tests/test_graph.py
from kumo import graph


def test_every_link_points_at_a_real_primary_key():
    """Kumo supports only foreign-key-to-primary-key links. A link whose
    destination has no primary key is silently useless."""
    from kumo import tables
    for link in graph.LINKS:
        dest = tables.CORE_TABLES[link.destination_table]
        assert dest.primary_key is not None, (
            f"{link.destination_table} is a link destination with no "
            f"primary key")


def test_the_fact_table_reaches_every_dimension():
    """career_metrics is the hub. If any of these edges is missing the graph
    is a set of islands and predictions quietly get worse rather than fail."""
    edges = {(l.source_table, l.foreign_key, l.destination_table)
             for l in graph.LINKS}
    for fk, dest in [
        ("author_id", "authors"),
        ("edition_id", "editions"),
        ("institution_id", "institutions"),
        ("field_id", "fields"),
        ("subfield_1_id", "subfields"),
        ("country_code", "countries"),
    ]:
        assert ("career_metrics", fk, dest) in edges, f"missing {fk} edge"


def test_referential_integrity_holds_in_the_data():
    """The Postgres load enforced 19 foreign keys, but the Parquet export is
    a separate path. Verify the keys actually resolve, because Kumo will not
    tell us if they do not."""
    problems = graph.validate_links()
    assert problems == [], "\n".join(problems)


def test_no_link_targets_a_table_outside_the_core_graph():
    from kumo import tables
    for link in graph.LINKS:
        assert link.source_table in tables.CORE_TABLES
        assert link.destination_table in tables.CORE_TABLES
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest kumo/tests/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kumo.graph'`

- [ ] **Step 3: Write `kumo/graph.py`**

```python
"""The graph schema: which tables link to which, and how to hand that to Kumo.

Kumo only supports foreign-key-to-primary-key links, which are many-to-one.
career_metrics is the fact table and every other core table is a dimension it
points at. Note that subfield_1_id and subfield_2_id both point at subfields:
two foreign keys from one source to one destination is allowed and is exactly
what the published data means (an author's two largest subfields).
"""
from dataclasses import dataclass

from kumo import tables


@dataclass(frozen=True)
class Link:
    source_table: str
    foreign_key: str
    destination_table: str


LINKS: list[Link] = [
    Link("career_metrics", "author_id", "authors"),
    Link("career_metrics", "edition_id", "editions"),
    Link("career_metrics", "institution_id", "institutions"),
    Link("career_metrics", "field_id", "fields"),
    Link("career_metrics", "subfield_1_id", "subfields"),
    Link("career_metrics", "subfield_2_id", "subfields"),
    Link("career_metrics", "country_code", "countries"),
    Link("institutions", "country_code", "countries"),
]


def build_metadata() -> dict:
    """The payload for the MCP update_graph_metadata tool."""
    return {
        "tables": [
            {
                "name": spec.name,
                "path": spec.path,
                "primary_key": spec.primary_key,
                "time_column": spec.time_column,
                "stypes": spec.stypes,
            }
            for spec in tables.CORE_TABLES.values()
        ],
        "links": [
            {
                "source_table": l.source_table,
                "foreign_key": l.foreign_key,
                "destination_table": l.destination_table,
            }
            for l in LINKS
        ],
    }


def validate_links() -> list[str]:
    """Check that every foreign key value resolves to a primary key value.

    NULL foreign keys are allowed and expected: 22,327 career rows have no
    institution and 33,370 have no country, which matches the source
    spreadsheets' empty cells. An unresolvable non-NULL key is a real bug.
    """
    problems: list[str] = []
    cache: dict[str, set] = {}

    for link in LINKS:
        dest_spec = tables.CORE_TABLES[link.destination_table]
        if link.destination_table not in cache:
            dest = tables.load(link.destination_table)
            cache[link.destination_table] = set(
                dest[dest_spec.primary_key].dropna().unique())
        keys = cache[link.destination_table]

        src = tables.load(link.source_table)
        values = src[link.foreign_key].dropna().unique()
        missing = [v for v in values if v not in keys]
        if missing:
            problems.append(
                f"{link.source_table}.{link.foreign_key} -> "
                f"{link.destination_table}: {len(missing)} value(s) do not "
                f"resolve, e.g. {missing[:3]}")
        del src

    return problems
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest kumo/tests/test_graph.py -v`
Expected: PASS, 4 tests. `test_referential_integrity_holds_in_the_data` is slow (it loads the fact table several times); that is acceptable for a correctness gate that runs rarely.

If it fails, the Parquet export has drifted from the Postgres schema. Report which key fails and how many rows, and fix `pipeline/build_relational.py`, not the test.

- [ ] **Step 5: Commit**

```bash
git add kumo/graph.py kumo/tests/test_graph.py
git commit -m "kumo: graph links, with a check that every foreign key resolves"
```

---

### Task 3: Authenticate, materialize, and land the first prediction

This is the first task that talks to Kumo's servers. It needs `KUMO_API_KEY` in the environment, or it will open a browser for OAuth2. **If no key is available and no browser flow can complete, stop and report BLOCKED** rather than stubbing the call: every number after this point has to come from a real response.

**Files:**
- Create: `kumo/session.py`
- Create: `kumo/queries.py`
- Create: `kumo/run_query.py`
- Test: `kumo/tests/test_queries.py`

**Interfaces:**
- Consumes: `kumo.graph.build_metadata`.
- Produces:
  - `kumo.session.materialize() -> kumoai.experimental.rfm.KumoRFM`: authenticates, registers tables and links, materializes, returns the model. Caches the model in a module global so repeated calls are cheap.
  - `kumo.queries.DROPOUT: str`, and one module-level constant per demo query.
  - `kumo.run_query.sample_entities(table: str, n: int, seed: int) -> list`: draws at most 1000 entity ids.

- [ ] **Step 1: Write the failing test**

These tests are about the query strings, not the network, so they run without an API key.

```python
# kumo/tests/test_queries.py
import re

import pytest

from kumo import queries

ALL = {name: getattr(queries, name)
       for name in dir(queries) if name.isupper()}


def test_every_query_has_predict_and_for_each():
    """Both keywords are mandatory in PQL."""
    for name, q in ALL.items():
        assert "PREDICT" in q, name
        assert "FOR EACH" in q, name


def test_no_sql_keywords_leak_in():
    """PQL is not SQL. JOIN/SELECT/GROUP BY/UNION are not supported and
    would fail server-side after a slow round trip."""
    banned = ("JOIN", "SELECT ", "GROUP BY", "UNION")
    for name, q in ALL.items():
        for word in banned:
            assert word not in q.upper(), f"{name} contains {word}"


def test_no_arithmetic():
    """PQL has no + or - operators. A minus sign is legal only as part of a
    negative offset inside an aggregation."""
    for name, q in ALL.items():
        assert "+" not in q, name


def test_columns_are_fully_qualified():
    """All column references must be table.column."""
    for name, q in ALL.items():
        for m in re.finditer(r"FOR EACH ([A-Za-z_0-9.]+)", q):
            assert "." in m.group(1), f"{name}: {m.group(1)}"


def test_list_distinct_queries_rank_top_at_most_20():
    for name, q in ALL.items():
        if "LIST_DISTINCT" not in q:
            continue
        m = re.search(r"RANK TOP (\d+)", q)
        assert m, f"{name}: LIST_DISTINCT requires RANK TOP k"
        assert 1 <= int(m.group(1)) <= 20, f"{name}: k out of range"


def test_temporal_entity_filters_are_backward_looking():
    """WHERE-clause aggregations must have start < 0 and end <= 0."""
    for name, q in ALL.items():
        where = q.split("WHERE", 1)
        if len(where) == 1:
            continue
        for start, end in re.findall(
                r"\(\s*[\w.*]+\s*,\s*(-?\w+)\s*,\s*(-?\d+)", where[1]):
            assert start.startswith("-"), f"{name}: start {start} not < 0"
            assert int(end) <= 0, f"{name}: end {end} not <= 0"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest kumo/tests/test_queries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kumo.queries'`

- [ ] **Step 3: Write `kumo/queries.py`**

```python
"""The demo's predictive queries.

Every one of these was written against the grammar the kumo-rfm-mcp package
ships at kumo://docs/predictive-query, not against a recollection of it. The
constraints that shaped them are in the plan's Global Constraints.

Editions are annual, so the natural window is 12 months and there are only
eight career snapshots. That coarseness is real and is reported alongside the
results rather than hidden.
"""

# 1. Top-2% dropout. Their flagship churn shape. Remaining on the list is a
#    threshold on rank within a subfield, so this is competitive: an author
#    can do everything right and still fall off because others did better.
DROPOUT = (
    "PREDICT COUNT(career_metrics.*, 0, 12, months) = 0 "
    "FOR EACH authors.author_id "
    "WHERE COUNT(career_metrics.*, -12, 0, months) > 0"
)

# 2. Next-edition composite score. Included to be honest about a weak
#    question: career metrics are cumulative since 1960, so next year's c is
#    nearly this year's c and a good score here means little.
NEXT_SCORE = (
    "PREDICT AVG(career_metrics.c, 0, 12, months) "
    "FOR EACH authors.author_id "
    "WHERE COUNT(career_metrics.*, -12, 0, months) > 0"
)

# 3. Next affiliation, as temporal link prediction over the institution
#    foreign key. Genuinely hard: affiliation is itself Scopus's ML guess at
#    one of several, and we measured it only 69-84% stable year to year.
NEXT_AFFILIATION = (
    "PREDICT LIST_DISTINCT(career_metrics.institution_id, 0, 12, months) "
    "RANK TOP 10 "
    "FOR EACH authors.author_id"
)

# 4. Retraction exposure. The centrepiece. nc_rw is NULL for every career
#    edition 2017-2022 and present for 2023-2024, and unlike np_rw (96.7%
#    zero) it is 71-76% nonzero, so it is a real target rather than a
#    degenerate one. Static imputation: the entity is the fact row.
RETRACTION_EXPOSURE = (
    "PREDICT career_metrics.nc_rw "
    "FOR EACH career_metrics.metric_id"
)

# The balanced binary form of the same question, which gives an AUROC that
# is meaningful rather than a regression error dominated by a long tail.
RETRACTION_EXPOSED = (
    "PREDICT career_metrics.nc_rw > 0 "
    "FOR EACH career_metrics.metric_id"
)

# The deliberately harder rare-event case, reported as such: an author's own
# retracted papers, positive in only 3.3-3.8% of rows.
OWN_RETRACTIONS = (
    "PREDICT career_metrics.np_rw > 0 "
    "FOR EACH career_metrics.metric_id"
)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest kumo/tests/test_queries.py -v`
Expected: PASS.

- [ ] **Step 5: Write `kumo/session.py`**

```python
"""Authenticate, register the graph, materialize it once.

Materialization is expensive and the model is reusable, so it is cached in a
module global. Nothing here catches an authentication failure and continues:
a demo that silently runs without a real model is worse than one that stops.
"""
import logging
import os

import pandas as pd
from kumoai.experimental import rfm

from kumo import graph, tables

logger = logging.getLogger(__name__)

_model: rfm.KumoRFM | None = None


def authenticate() -> None:
    """Authenticate from KUMO_API_KEY, or fall back to the browser flow.

    Never log the key. rfm.authenticate() sets KUMO_API_KEY itself on a
    successful OAuth2 round trip.
    """
    if os.getenv("KUMO_API_KEY"):
        logger.info("authenticating from KUMO_API_KEY")
    else:
        logger.info("KUMO_API_KEY unset; opening the OAuth2 browser flow")
    rfm.authenticate()


def materialize(force: bool = False) -> rfm.KumoRFM:
    """Build the graph from CORE_TABLES and LINKS and materialize it."""
    global _model
    if _model is not None and not force:
        return _model

    authenticate()

    local_tables = {}
    for name, spec in tables.CORE_TABLES.items():
        df = tables.load(name)
        # Verified signature:
        #   LocalTable(df, name, primary_key=..., time_column=...,
        #              end_time_column=...)
        # primary_key and time_column are constructor arguments, not
        # attributes to assign afterwards.
        table = rfm.LocalTable(
            df=df,
            name=name,
            primary_key=spec.primary_key,
            time_column=spec.time_column,
        )
        for column, stype in spec.stypes.items():
            if column in df.columns:
                table[column].stype = stype
        local_tables[name] = table
        logger.info("registered %s: %d rows, %d columns",
                    name, len(df), df.shape[1])

    local_graph = rfm.LocalGraph(tables=list(local_tables.values()))
    for link in graph.LINKS:
        local_graph.link(
            src_table=link.source_table,
            fkey=link.foreign_key,
            dst_table=link.destination_table,
        )

    _model = rfm.KumoRFM(local_graph)
    logger.info("graph materialized")
    return _model
```

These signatures were read from the installed package rather than assumed:

```
LocalTable(df, name, primary_key=<MissingType|str|None>, time_column=None,
           end_time_column=None)
Graph(tables, edges=None)                      # rfm.LocalGraph is rfm.Graph
Graph.link(src_table, fkey, dst_table) -> Self
KumoRFM(graph, verbose=True, optimize=False)
```

Confirm them once more in this environment before relying on them, since the
package is unpinned below `kumo-rfm-mcp`:

```bash
.venv/bin/python -c "
import inspect
from kumoai.experimental import rfm
print(inspect.signature(rfm.LocalTable.__init__))
print(inspect.signature(rfm.LocalGraph.link))
"
```

If they differ, correct `materialize()` and record the difference in the task
report rather than bending the rest of the plan around a guess.

- [ ] **Step 6: Write `kumo/run_query.py`**

```python
"""Run one named query against the materialized graph and save the result.

Kumo accepts at most 1000 entities per call, so every run here is a sample.
Full-table passes are Task 5's batched job, not this.
"""
import argparse
import json
import logging
from pathlib import Path

from kumo import queries, session, tables

OUT = Path(__file__).resolve().parent / "out"
MAX_ENTITIES = 1000


def sample_entities(table: str, n: int = 1000, seed: int = 20260914) -> list:
    """Draw at most MAX_ENTITIES primary key values from a table."""
    n = min(n, MAX_ENTITIES)
    spec = tables.CORE_TABLES[table]
    df = tables.load(table)
    return (df[spec.primary_key]
            .dropna()
            .sample(n=min(n, len(df)), random_state=seed)
            .tolist())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="a constant name in kumo.queries")
    parser.add_argument("--entity-table", default="authors")
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--run-mode", default="fast",
                        choices=["fast", "normal", "best"])
    parser.add_argument("--evaluate", action="store_true",
                        help="evaluate against known truth instead of "
                             "predicting")
    parser.add_argument("--anchor-time", default=None,
                        help="'entity' for static queries over temporal "
                             "facts, otherwise leave unset")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    query = getattr(queries, args.query)
    model = session.materialize()
    indices = sample_entities(args.entity_table, args.n)

    # evaluate() takes NO indices argument -- it selects its own in-context
    # examples from the graph. Only predict() is entity-scoped, and only
    # predict() is subject to the 1000-entity cap.
    if args.evaluate:
        result = model.evaluate(query, run_mode=args.run_mode,
                                anchor_time=args.anchor_time)
    else:
        result = model.predict(query, indices=indices,
                               run_mode=args.run_mode,
                               anchor_time=args.anchor_time)

    OUT.mkdir(exist_ok=True)
    stem = f"{args.query.lower()}_{'eval' if args.evaluate else 'pred'}"
    result.to_parquet(OUT / f"{stem}.parquet")
    print(result.to_string(max_rows=20))
    (OUT / f"{stem}.meta.json").write_text(json.dumps({
        "query": query, "entity_table": args.entity_table,
        "n": len(indices), "run_mode": args.run_mode,
        "anchor_time": args.anchor_time,
    }, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the dropout query for real**

```bash
.venv/bin/python -m kumo.run_query DROPOUT --entity-table authors --n 1000
.venv/bin/python -m kumo.run_query DROPOUT --entity-table authors --n 1000 --evaluate
```

Expected: a binary classification frame with `ENTITY`, `ANCHOR_TIMESTAMP`, `TARGET_PRED`, `False_PROB`, `True_PROB`, and an evaluation carrying `auroc`, `auprc`, `precision`, `recall`, `f1`, `acc`.

**Paste the real evaluation output into the task report, including the in-context label distribution from the logs.** If AUROC is near 0.5, say so plainly and record the label distribution rather than re-running until a better number appears.

- [ ] **Step 8: Commit**

```bash
git add kumo/session.py kumo/queries.py kumo/run_query.py kumo/tests/test_queries.py
git commit -m "kumo: authenticate, materialize the graph, run the dropout query"
```

---

### Task 4: The second and third queries, and an honest report on the weak one

**Files:**
- Create: `kumo/report.py`
- Modify: `kumo/run_query.py`
- Test: `kumo/tests/test_report.py`

**Interfaces:**
- Consumes: `kumo.run_query`, the Parquet outputs in `kumo/out/`.
- Produces: `kumo.report.summarize(stem: str) -> dict` and a written `kumo/out/RESULTS.md`.

- [ ] **Step 1: Write the failing test**

```python
# kumo/tests/test_report.py
import pandas as pd
import pytest

from kumo import report


def test_summarize_refuses_a_missing_run(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "OUT", tmp_path)
    with pytest.raises(FileNotFoundError):
        report.summarize("nope_eval")


def test_summarize_reads_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "OUT", tmp_path)
    pd.DataFrame({"metric": ["auroc", "acc"],
                  "value": [0.81, 0.74]}).to_parquet(tmp_path / "x_eval.parquet")
    (tmp_path / "x_eval.meta.json").write_text('{"query": "PREDICT ..."}')
    out = report.summarize("x_eval")
    assert out["metrics"]["auroc"] == 0.81
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest kumo/tests/test_report.py -v`
Expected: FAIL, no module `kumo.report`.

- [ ] **Step 3: Write `kumo/report.py`**

```python
"""Collect the saved runs into one results document.

The point of writing this down mechanically is that the demo's claims then
come from files that a reader can regenerate, rather than from a summary
someone typed.
"""
import json
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "out"


def summarize(stem: str) -> dict:
    frame = OUT / f"{stem}.parquet"
    if not frame.exists():
        raise FileNotFoundError(f"no saved run at {frame}")
    df = pd.read_parquet(frame)
    meta = json.loads((OUT / f"{stem}.meta.json").read_text())

    metrics = {}
    if {"metric", "value"}.issubset(df.columns):
        metrics = dict(zip(df["metric"], df["value"]))
    return {"stem": stem, "meta": meta, "metrics": metrics, "rows": len(df)}


def write_results(stems: list[str]) -> Path:
    lines = ["# KumoRFM results", ""]
    for stem in stems:
        try:
            s = summarize(stem)
        except FileNotFoundError:
            lines += [f"## {stem}", "", "Not run.", ""]
            continue
        lines += [f"## {stem}", "",
                  "```", s["meta"].get("query", ""), "```", ""]
        if s["metrics"]:
            lines += ["| metric | value |", "|---|---|"]
            lines += [f"| {k} | {v:.4f} |" for k, v in s["metrics"].items()]
        else:
            lines.append(f"{s['rows']} predictions.")
        lines.append("")
    path = OUT / "RESULTS.md"
    path.write_text("\n".join(lines))
    return path
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest kumo/tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Run queries 2 and 3 for real**

```bash
.venv/bin/python -m kumo.run_query NEXT_SCORE --n 1000 --evaluate
.venv/bin/python -m kumo.run_query NEXT_AFFILIATION --n 1000 --evaluate
```

Expected: `NEXT_SCORE` returns regression metrics (`mae`, `rmse`, `r2`, `smape`); `NEXT_AFFILIATION` returns link-prediction metrics (`map@k`, `ndcg@k`, `mrr@k`, `hit_ratio@k`).

**`NEXT_SCORE` is expected to score very well and that is the finding, not the achievement.** `c` is cumulative since 1960, so last year's value nearly determines this year's. Record the r2 and state the leakage plainly in the report. A baseline worth one line: how well does "predict this author's previous `c`" do? If it matches Kumo, say so.

- [ ] **Step 6: Commit**

```bash
git add kumo/report.py kumo/tests/test_report.py kumo/out/RESULTS.md
git commit -m "kumo: score and affiliation queries, with the leakage stated"
```

---

### Task 5: Retraction-exposure backfill, the centrepiece

The three retraction columns exist only for 2023 and 2024. Every earlier career edition is 100% NULL, verified. The demonstration is: hold out the years where truth is known, measure, then impute the six years nobody has.

**Files:**
- Create: `kumo/backfill.py`
- Test: `kumo/tests/test_backfill.py`

**Interfaces:**
- Consumes: `kumo.session.materialize`, `kumo.queries.RETRACTION_EXPOSURE`, `kumo.queries.RETRACTION_EXPOSED`.
- Produces:
  - `kumo.backfill.null_metric_ids() -> list[int]`: the fact rows needing imputation.
  - `kumo.backfill.batches(ids: list, size: int = 1000) -> Iterator[list]`.
  - `kumo.backfill.run(limit: int | None) -> Path`: writes `kumo/out/retraction_backfill.parquet`, resumable.

- [ ] **Step 1: Write the failing test**

```python
# kumo/tests/test_backfill.py
import pytest

from kumo import backfill


def test_batches_never_exceed_the_api_cap():
    """predict accepts at most 1000 entities. A batch of 1001 fails at the
    server after a slow round trip."""
    ids = list(range(2500))
    chunks = list(backfill.batches(ids, size=1000))
    assert [len(c) for c in chunks] == [1000, 1000, 500]
    assert sum(len(c) for c in chunks) == len(ids)


def test_batches_rejects_an_oversized_request():
    with pytest.raises(ValueError):
        list(backfill.batches([1, 2, 3], size=1001))


def test_null_rows_are_exactly_the_pre_2023_editions():
    """nc_rw is NULL for career-2017..career-2022 and present for 2023-2024.
    If this stops being true the backfill is imputing the wrong rows."""
    import pandas as pd
    from kumo import tables
    df = tables.load("career_metrics")
    null_editions = set(df.loc[df["nc_rw"].isna(), "edition_id"].unique())
    present_editions = set(df.loc[df["nc_rw"].notna(), "edition_id"].unique())
    assert null_editions == {
        "career-2017", "career-2018", "career-2019",
        "career-2020", "career-2021", "career-2022"}
    assert present_editions == {"career-2023", "career-2024"}
    assert not (null_editions & present_editions)


def test_null_count_matches_the_measured_total():
    """955,512 career rows have no retraction data: the sum of the six
    editions that predate tracking (105,026 + 105,000 + 159,683 + 186,177
    + 194,983 + 204,643). At 1000 entities per call that is 956 calls."""
    from kumo import tables
    df = tables.load("career_metrics")
    assert int(df["nc_rw"].isna().sum()) == 955512
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest kumo/tests/test_backfill.py -v`
Expected: FAIL, no module `kumo.backfill`.

- [ ] **Step 3: Write `kumo/backfill.py`**

```python
"""Impute retraction exposure for the career editions that predate tracking.

The three retraction columns arrived with Mendeley version 7. career-2017
through career-2022 are NULL for all of them -- not zero, NULL -- because
nothing was tracked, not because nothing was retracted. That is a genuine
missing-value problem with a built-in validation set: 2023 and 2024, where
the truth is known.

This is a static imputation query, so the entity is the fact row rather than
the author, and anchor_time='entity' keeps a 2018 row from seeing 2024 data.
"""
import json
import logging
from pathlib import Path
from typing import Iterator

import pandas as pd

from kumo import queries, session, tables

logger = logging.getLogger(__name__)
OUT = Path(__file__).resolve().parent / "out"
MAX_ENTITIES = 1000


def batches(ids: list, size: int = MAX_ENTITIES) -> Iterator[list]:
    if size > MAX_ENTITIES:
        raise ValueError(
            f"Kumo accepts at most {MAX_ENTITIES} entities per call, "
            f"got {size}")
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def null_metric_ids() -> list[int]:
    df = tables.load("career_metrics")
    return df.loc[df["nc_rw"].isna(), "metric_id"].tolist()


def run(limit: int | None = None, run_mode: str = "fast") -> Path:
    """Impute nc_rw for the NULL rows, resuming from whatever is saved."""
    OUT.mkdir(exist_ok=True)
    partial = OUT / "retraction_backfill.parquet"

    done: set = set()
    frames: list[pd.DataFrame] = []
    if partial.exists():
        existing = pd.read_parquet(partial)
        frames.append(existing)
        done = set(existing["ENTITY"])
        logger.info("resuming: %d rows already imputed", len(done))

    todo = [i for i in null_metric_ids() if i not in done]
    if limit is not None:
        todo = todo[:limit]
    logger.info("%d rows to impute, %d calls",
                len(todo), -(-len(todo) // MAX_ENTITIES))

    model = session.materialize()
    for n, chunk in enumerate(batches(todo), start=1):
        result = model.predict(
            queries.RETRACTION_EXPOSURE,
            indices=chunk,
            anchor_time="entity",
            run_mode=run_mode,
        )
        frames.append(result)
        # Checkpoint every call: 956 calls is long enough that losing the
        # lot to one network error would be painful.
        pd.concat(frames, ignore_index=True).to_parquet(partial)
        logger.info("batch %d: %d rows (%d total)",
                    n, len(result), sum(len(f) for f in frames))

    return partial


def evaluate_on_known_years(run_mode: str = "fast") -> dict:
    """Measure where nc_rw is actually known.

    evaluate() takes no indices: it draws its own in-context examples and
    holds out labelled ones to score against. Since nc_rw is only non-NULL
    for career-2023 and career-2024, those are the only rows that can carry
    a label, so the evaluation is automatically confined to them without us
    having to pass a sample.
    """
    model = session.materialize()
    out = {}
    for name, query in [("regression", queries.RETRACTION_EXPOSURE),
                        ("binary", queries.RETRACTION_EXPOSED),
                        ("own_retractions", queries.OWN_RETRACTIONS)]:
        result = model.evaluate(query, anchor_time="entity",
                                run_mode=run_mode)
        out[name] = dict(zip(result["metric"], result["value"]))
        logger.info("%s: %s", name, out[name])

    OUT.mkdir(exist_ok=True)
    (OUT / "retraction_eval.json").write_text(json.dumps(out, indent=2))
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest kumo/tests/test_backfill.py -v`
Expected: PASS. Record the real NULL count in the report.

- [ ] **Step 5: Evaluate on the years where truth is known**

```bash
.venv/bin/python -c "
import logging; logging.basicConfig(level=logging.INFO)
from kumo import backfill
backfill.evaluate_on_known_years()
"
```

Expected: three metric sets. The one that matters is `binary` (AUROC on `nc_rw > 0`, a 71-76% positive rate). `own_retractions` is the rare-event case at 3.3-3.8% positive, where AUROC and average precision will be much weaker.

**Report all three, including the weak one.** A demo that shows only the query that worked is the kind of thing the audience does this for a living and will notice. Also record the trivial baseline: predicting the majority class gives roughly 0.71 accuracy on `binary` and roughly 0.96 on `own_retractions`, which is exactly why accuracy is the wrong metric there and AUROC is quoted instead.

- [ ] **Step 6: Run a bounded backfill**

```bash
.venv/bin/python -c "
import logging; logging.basicConfig(level=logging.INFO)
from kumo import backfill
backfill.run(limit=10000)
"
```

Expected: 10 calls, 10,000 imputed rows, checkpointed. Time the calls and extrapolate the full 956-call job in the report rather than running it blind. **Do not launch the full backfill without checking Kumo's free-tier rate limits first**; if the bounded run hits a limit, record the limit and stop.

- [ ] **Step 7: Commit**

```bash
git add kumo/backfill.py kumo/tests/test_backfill.py
git commit -m "kumo: retraction-exposure imputation, validated on 2023-2024"
```

---

### Task 6: OpenAlex co-authorship enrichment

The spec calls this "the single most valuable addition in the design", and the reason is structural: without it every path between two authors runs through an institution or a field, which is thin. Co-authorship makes it a network.

The full OpenAlex snapshot is hundreds of gigabytes and downloading it for this is disproportionate. **Ruling: link a stratified sample, not the whole corpus.** The sample must be large enough to support the entity-resolution evaluation in Task 7 and to add real co-authorship edges, and small enough to fetch within the free API allowance.

**Files:**
- Create: `kumo/openalex/fetch.py`
- Create: `kumo/openalex/link.py`
- Test: `kumo/tests/test_openalex_link.py`

**Interfaces:**
- Consumes: `data_parquet/authors.parquet`.
- Produces:
  - `data_parquet/openalex_authors.parquet`: `openalex_id`, `display_name`, `orcid`, `works_count`, `cited_by_count`, `last_known_institution`.
  - `data_parquet/author_openalex_links.parquet`: `author_id`, `openalex_id`, `match_score`, `match_method`.
  - `kumo.openalex.link.candidates(name: str) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# kumo/tests/test_openalex_link.py
from kumo.openalex import link


def test_name_to_query_form_inverts_the_scopus_convention():
    """Scopus publishes 'Surname, Given'; OpenAlex indexes 'Given Surname'.
    Searching the raw Scopus string finds nothing."""
    assert link.to_query_form("Ioannidis, John P.A.") == "John P.A. Ioannidis"
    assert link.to_query_form("Dahmen, Ulrich") == "Ulrich Dahmen"


def test_name_without_a_comma_passes_through():
    assert link.to_query_form("Madonna") == "Madonna"


def test_compound_surnames_survive():
    """The comma is the separator, not the first space -- the same trap that
    broke block_key in plan 1."""
    assert link.to_query_form("van der Berg, Jan") == "Jan van der Berg"


def test_score_prefers_an_orcid_match_over_a_name_match():
    a = {"orcid": "0000-0001", "display_name": "Jan van der Berg"}
    b = {"orcid": None, "display_name": "Jan van der Berg"}
    assert link.score("van der Berg, Jan", a) > link.score("van der Berg, Jan", b)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest kumo/tests/test_openalex_link.py -v`
Expected: FAIL, no module `kumo.openalex`.

- [ ] **Step 3: Write `kumo/openalex/link.py`**

```python
"""Match our Scopus-derived authors to OpenAlex authors.

Two things make this harder than a string compare. Scopus publishes
"Surname, Given" and OpenAlex indexes "Given Surname", so the raw string
finds nothing. And this is itself an entity resolution problem -- the very
problem Task 7 asks Kumo about -- so the links produced here are evidence,
not ground truth, and are scored rather than asserted.
"""
from __future__ import annotations

import unicodedata


def to_query_form(authfull: str) -> str:
    """Turn 'Surname, Given' into 'Given Surname'.

    Split on the comma first and only then strip, exactly as plan 1's
    block_key has to: normalising first would remove the comma and a
    compound surname like 'van der Berg' would lose its structure.
    """
    if "," not in authfull:
        return authfull.strip()
    surname, given = authfull.split(",", 1)
    return f"{given.strip()} {surname.strip()}".strip()


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").casefold().strip()


def score(authfull: str, candidate: dict) -> float:
    """A deliberately simple, explainable score in [0, 1].

    An ORCID on the candidate is worth a lot because it means OpenAlex has
    an externally anchored identity rather than only its own clustering.
    """
    s = 0.0
    if _norm(candidate.get("display_name", "")) == _norm(to_query_form(authfull)):
        s += 0.6
    if candidate.get("orcid"):
        s += 0.3
    if candidate.get("works_count", 0) > 10:
        s += 0.1
    return min(s, 1.0)


def candidates(name: str) -> list[dict]:
    """Look up candidate OpenAlex authors for a name. Implemented in fetch."""
    from kumo.openalex import fetch
    return fetch.search_authors(to_query_form(name))
```

- [ ] **Step 4: Write `kumo/openalex/fetch.py`**

Respect the February 2026 pricing change: the API now needs a free key with a daily allowance. Read it from `OPENALEX_API_KEY` and always send a mailto in the user agent, which is the documented polite-pool convention.

```python
"""Fetch OpenAlex authors for a sampled subset of ours.

Deliberately not the bulk snapshot. The full snapshot is hundreds of
gigabytes and this needs a few tens of thousands of authors, so the API with
a free key is the proportionate tool. Requests are cached on disk so a rerun
costs nothing against the daily allowance.
"""
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent / "out" / "openalex_cache"
BASE = "https://api.openalex.org/authors"
MAILTO = os.getenv("OPENALEX_MAILTO", "")


def search_authors(query: str, per_page: int = 5) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (urllib.parse.quote(query, safe="")[:150] + ".json")
    if key.exists():
        return json.loads(key.read_text())

    params = {"search": query, "per-page": per_page}
    if MAILTO:
        params["mailto"] = MAILTO
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]

    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": f"twopercenters/1.0 ({MAILTO})"})

    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except Exception as exc:                       # noqa: BLE001
            if attempt == 2:
                raise
            logger.warning("openalex %s failed (%s), retrying", query, exc)
            time.sleep(2 ** attempt)

    results = [
        {
            "openalex_id": r.get("id"),
            "display_name": r.get("display_name"),
            "orcid": r.get("orcid"),
            "works_count": r.get("works_count", 0),
            "cited_by_count": r.get("cited_by_count", 0),
        }
        for r in payload.get("results", [])
    ]
    key.write_text(json.dumps(results))
    return results
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest kumo/tests/test_openalex_link.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 6: Link a stratified sample**

Draw 20,000 authors stratified by `is_ambiguous` and by whether they appear on both sides of the 2023-2024 boundary, so the sample is informative for Task 7 rather than merely large. Write `data_parquet/author_openalex_links.parquet`.

**Report the linkage rate and the score distribution.** A low rate is a finding about how hard this problem is, not a failure to hide. If the daily allowance runs out, record how far it got and resume the next day; the on-disk cache makes that free.

- [ ] **Step 7: Commit**

```bash
git add kumo/openalex/ kumo/tests/test_openalex_link.py
git commit -m "kumo: link a stratified author sample to OpenAlex"
```

---

### Task 7: Entity resolution as link prediction, against the 85.2% baseline

The spec is careful here and this task should stay careful: this is presented as the open problem, not a finished result. There is a deterministic baseline of 85.2% on the 2023-2024 boundary and a defined residual.

The obstacle is that PQL does not express "which 2023 author is this 2024 author". `LIST_DISTINCT` ranks foreign key values, so the question needs a candidate-link table with a foreign key to each side, built before the query. That construction is the task.

**Files:**
- Create: `kumo/entity_resolution.py`
- Test: `kumo/tests/test_entity_resolution.py`

**Interfaces:**
- Consumes: `data_parquet/author_name_observations.parquet`, `data_parquet/author_openalex_links.parquet`.
- Produces:
  - `data_parquet/er_candidates.parquet`: `candidate_id`, `left_author_id`, `right_author_id`, `block_key`, `is_match_baseline`, `observation_date`.
  - `kumo.entity_resolution.baseline_rate() -> float`.

- [ ] **Step 1: Write the failing test**

```python
# kumo/tests/test_entity_resolution.py
import pytest

from kumo import entity_resolution as er


def test_candidates_are_blocked_not_crossed():
    """230,333 x 217,097 is 50 billion pairs. Blocking on surname and first
    initial is what makes this finite; a full cross product is a bug, not a
    slow path."""
    pairs = er.candidate_pairs(
        left=[{"author_id": "a", "surname": "smith", "first_initial": "j"}],
        right=[{"author_id": "b", "surname": "smith", "first_initial": "j"},
               {"author_id": "c", "surname": "jones", "first_initial": "j"}],
    )
    assert [(p["left_author_id"], p["right_author_id"]) for p in pairs] == [("a", "b")]


def test_baseline_flag_marks_the_deterministic_match():
    """The 85.2% baseline is surname + first initial + firstyr."""
    pairs = er.candidate_pairs(
        left=[{"author_id": "a", "surname": "smith",
               "first_initial": "j", "firstyr": 1990}],
        right=[{"author_id": "b", "surname": "smith",
                "first_initial": "j", "firstyr": 1990},
               {"author_id": "c", "surname": "smith",
                "first_initial": "j", "firstyr": 2001}],
    )
    flags = {p["right_author_id"]: p["is_match_baseline"] for p in pairs}
    assert flags == {"b": True, "c": False}


def test_a_left_author_with_no_block_partner_yields_nothing():
    assert er.candidate_pairs(
        left=[{"author_id": "a", "surname": "zzz", "first_initial": "q"}],
        right=[{"author_id": "b", "surname": "smith", "first_initial": "j"}],
    ) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest kumo/tests/test_entity_resolution.py -v`
Expected: FAIL, no module `kumo.entity_resolution`.

- [ ] **Step 3: Implement `kumo/entity_resolution.py`**

Build candidate pairs by blocking on `surname` + `first_initial` (the same blocking plan 1 uses, and the same comma-before-normalise rule). Flag `is_match_baseline` where `firstyr` also agrees. Write the candidate table with its own primary key and foreign keys to `authors` on both sides.

Note the asymmetry that makes this a real question: the baseline links 181,334 of the 2024 authors (85.2%), leaving roughly 31,000 unmatched plus the multi-person name blocks. Those residual pairs are where link prediction has something to prove.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest kumo/tests/test_entity_resolution.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Register the candidate table and ask Kumo**

Add `er_candidates` to the graph with foreign keys to `authors` on both sides, then evaluate:

```
PREDICT er_candidates.is_match_baseline = True
FOR EACH er_candidates.candidate_id
```

Train-and-measure on the pairs the baseline is confident about, then **apply to the residual pairs the baseline could not match** and report how many it resolves, with OpenAlex links as the external check where they exist.

**State the result as a question answered, in either direction.** If link prediction does not beat 85.2%, that is a publishable finding about this dataset and it belongs in the report exactly as clearly as a win would.

- [ ] **Step 6: Commit**

```bash
git add kumo/entity_resolution.py kumo/tests/test_entity_resolution.py
git commit -m "kumo: entity resolution as link prediction over candidate pairs"
```

---

### Task 8: The agentic layer, in the dashboard

The natural-language box turns a question into PQL, runs it, and charts the answer, with Kumo's own explanation rendered beside it. `predict()` takes an `explain` argument and returns an `Explanation`, so the reasoning comes from the same call rather than a second one.

Because the dependency split turned out not to exist, this is an ordinary Dash page importing an ordinary module. The one real constraint left is memory: the materialized graph is roughly 1.4 GB resident, and gunicorn runs two workers, so a page that materializes on demand costs about 2.8 GB on a host already running five other dashboards. The page is therefore behind an environment flag that is off by default.

**Files:**
- Create: `kumo/service.py`
- Create: `pages/predict.py`
- Test: `kumo/tests/test_service.py`, `tests/test_predict_page.py`

**Interfaces:**
- Produces:
  - `kumo.service.validate(query: str, n: int) -> None`: raises `ValueError` with a specific message on a malformed query.
  - `kumo.service.run(query: str, entity_table: str, n: int, explain: bool) -> dict`: returns `{"predictions": DataFrame, "explanation": str | None}`.
  - `kumo.service.enabled() -> bool`: whether `KUMO_ENABLED` is set.

- [ ] **Step 1: Write the failing test**

```python
# kumo/tests/test_service.py
import pytest

from kumo import service


def test_rejects_sql():
    """A natural-language box will produce SQL sooner or later. Reject it
    locally with a clear message rather than after a slow round trip."""
    with pytest.raises(ValueError, match="PQL"):
        service.validate("SELECT * FROM authors", n=10)


def test_rejects_more_than_1000_entities():
    with pytest.raises(ValueError, match="1000"):
        service.validate(
            "PREDICT career_metrics.nc_rw FOR EACH career_metrics.metric_id",
            n=5000)


def test_requires_both_keywords():
    with pytest.raises(ValueError, match="FOR EACH"):
        service.validate("PREDICT career_metrics.nc_rw", n=10)
    with pytest.raises(ValueError, match="PREDICT"):
        service.validate("FOR EACH authors.author_id", n=10)


def test_rejects_arithmetic():
    with pytest.raises(ValueError, match="arithmetic"):
        service.validate(
            "PREDICT career_metrics.nc_rw + 1 FOR EACH career_metrics.metric_id",
            n=10)


def test_list_distinct_needs_rank_top_within_range():
    base = ("PREDICT LIST_DISTINCT(career_metrics.institution_id, 0, 12, months) "
            "FOR EACH authors.author_id")
    with pytest.raises(ValueError, match="RANK TOP"):
        service.validate(base, n=10)
    with pytest.raises(ValueError, match="20"):
        service.validate(base.replace("FOR EACH", "RANK TOP 50 FOR EACH"), n=10)


def test_a_valid_query_passes():
    service.validate(
        "PREDICT COUNT(career_metrics.*, 0, 12, months) = 0 "
        "FOR EACH authors.author_id", n=1000)


def test_run_refuses_when_disabled(monkeypatch):
    """The dashboard must keep working with Kumo switched off, which is the
    normal state of the public deployment."""
    monkeypatch.delenv("KUMO_ENABLED", raising=False)
    assert service.enabled() is False
    with pytest.raises(RuntimeError, match="KUMO_ENABLED"):
        service.run("PREDICT x FOR EACH y.z", entity_table="authors", n=10)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest kumo/tests/test_service.py -v`
Expected: FAIL, no module `kumo.service`.

- [ ] **Step 3: Write `kumo/service.py`**

Validate before doing anything expensive, in this order, raising `ValueError` with a message naming the specific problem: both `PREDICT` and `FOR EACH` present; no SQL keyword (`SELECT`, `JOIN`, `GROUP BY`, `UNION`); no `+` arithmetic; `n` at most 1000; `LIST_DISTINCT` accompanied by `RANK TOP k` with 1 <= k <= 20.

```python
"""Run a predictive query on behalf of the dashboard.

Two things here are deliberate rather than incidental.

Kumo is imported lazily, inside run(), never at module import. The dashboard
must start and serve every other page on a host with no Kumo key and no
memory for a graph.

And the graph is materialized at most once per process, behind KUMO_ENABLED.
It is roughly 1.4 GB resident and gunicorn runs two workers, so leaving this
on by default would cost about 2.8 GB on a box that also runs five other
dashboards.
"""
import os
import re

MAX_ENTITIES = 1000
_SQL = ("SELECT", "JOIN", "GROUP BY", "UNION")


def enabled() -> bool:
    return os.getenv("KUMO_ENABLED", "").strip() not in ("", "0", "false")


def validate(query: str, n: int) -> None:
    upper = query.upper()
    if "PREDICT" not in upper:
        raise ValueError("A predictive query must contain PREDICT.")
    if "FOR EACH" not in upper:
        raise ValueError("A predictive query must contain FOR EACH.")
    for word in _SQL:
        if word in upper:
            raise ValueError(
                f"{word} is SQL, and PQL is not SQL. Joins, subqueries and "
                f"grouping are not supported.")
    if "+" in query:
        raise ValueError("PQL supports no arithmetic operations.")
    if n > MAX_ENTITIES:
        raise ValueError(
            f"Kumo accepts at most {MAX_ENTITIES} entities per query, "
            f"got {n}.")
    if "LIST_DISTINCT" in upper:
        match = re.search(r"RANK TOP (\d+)", upper)
        if not match:
            raise ValueError("LIST_DISTINCT requires a RANK TOP k clause.")
        if not 1 <= int(match.group(1)) <= 20:
            raise ValueError("RANK TOP k requires k between 1 and 20.")
```

`run()` validates, checks `enabled()`, then imports `kumo.session` and calls
`model.predict(query, indices=..., explain=explain)`. Return the frame and,
when `explain` is on, the `Explanation`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest kumo/tests/test_service.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Add the dashboard page**

`pages/predict.py` offers the demo queries from `kumo.queries` as presets rather than only a free-text box, since a preset that works beats a blank box that usually does not. When `KUMO_ENABLED` is unset the page renders an explanation of what it would do instead of erroring.

Two hazards from plan 1 apply directly and must not be repeated:

- **Do not read the database or materialize anything at module import.** That is precisely what forced `close_db()` in `app.py` and the `post_fork` hook in `cfg.py`. `tests/test_no_shared_connection.py` holds that invariant and must still pass.
- **Do not register the page at a guessable scratch route.** `pages/test.py` at `/keke` is the existing example of what not to do.

- [ ] **Step 6: Verify the dashboard is unharmed**

```bash
.venv/bin/pytest tests/ -v
.venv/bin/pytest kumo/tests/ -v
```

Expected: the dashboard's 118 tests still pass, unchanged. This is the check that matters most in this task: adding roughly 110 packages to a shared environment is exactly the kind of change that breaks something at a distance, and the suite is what proves it did not.

Also confirm the app still imports without Kumo present in memory:

```bash
.venv/bin/python -c "
import app, sys
assert 'kumoai' not in sys.modules, 'kumoai imported at dashboard import time'
print('clean import')
"
```

- [ ] **Step 7: Measure what the page costs before enabling it anywhere**

```bash
KUMO_ENABLED=1 .venv/bin/python -c "
import resource, sys
from kumo import session
session.materialize()
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print('peak RSS bytes:', peak)
"
```

Record the peak. Task 1 predicts roughly 1.4 GB for the tables themselves; whatever Kumo adds on top of that is the number that decides whether this page can ever run on the dokku host, and it belongs in the report.

- [ ] **Step 8: Commit**

```bash
git add kumo/service.py pages/predict.py kumo/tests/test_service.py tests/test_predict_page.py
git commit -m "kumo: a prediction page, off by default, with the memory measured"
```

---

## What this plan does not do

- **It does not enable predictions on dokku.** `KUMO_ENABLED` stays unset there. Two gunicorn workers each materializing a 1.4 GB graph on a box already running five dashboards is a capacity decision that needs Task 8's measured peak RSS first, and a separate process is the obvious answer if the number is bad.
- **It does not run the full 856-call backfill.** Task 5 runs a bounded 10,000-row pass and extrapolates, because the free-tier rate limits are unknown until something hits them.
- **It does not download the OpenAlex bulk snapshot.** Task 6 links a stratified 20,000-author sample through the API.
- **It does not add `singleyr_metrics` to the graph.** None of the five queries asks a single-year question, and it is a second 1.2 GB table.

## Open questions this plan will answer

1. Does the core graph materialize in acceptable memory and time? (Task 1, Task 3)
2. Is the `rfm.LocalTable` / `rfm.LocalGraph` API as assumed? (Task 3, Step 5)
3. What are Kumo's free-tier rate limits? (Task 5)
4. Does retraction exposure impute usefully, and how much worse is the rare-event variant? (Task 5)
5. Can link prediction beat the 85.2% deterministic entity-resolution baseline on the residual? (Task 7)
