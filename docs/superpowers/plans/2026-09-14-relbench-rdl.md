# RelBench Relational Deep Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the relational core built in plan 1 into a published RelBench dataset with four predictive tasks, trained and evaluated locally on Apple Silicon, with the results shown in the dashboard.

**Architecture:** A new top-level `rdl/` package in the existing virtualenv. It reindexes the Parquet tables from plan 1 into RelBench's bring-your-own-data layout, defines the tasks as manifests, and trains the reference heterogeneous GNN (`HeteroEncoder` + `HeteroGraphSAGE` from `relbench.modeling.nn`) on the MPS backend. Predictions are computed in batch and written to Postgres; the dashboard reads them like any other table and never imports torch.

The engine is deliberately swappable. The dataset directory, the task definitions and the time splits are all engine-independent, so if Kumo access arrives (see `docs/kumo-access-ask.md`), the same graph and the same tasks can be pointed at KumoRFM for a like-for-like comparison. That is the point of building it this way rather than hard-wiring a model.

**Tech Stack:** `relbench==3.0.1`, `pytorch_frame[full]==0.3.0`, `torch_geometric==2.8.0`, `torch==2.14.0` (MPS), pandas 1.5.2, **numpy 1.26.4**, Dash 2.15, Postgres 16.

**Spec:** `docs/superpowers/specs/2026-09-13-twopercenters-relational-redesign-design.md`

## Global Constraints

- **numpy moves from 1.21.5 to 1.26.4, and nothing else moves.** `pandas==1.5.2`, `pyarrow==17.0.0` and `runtime.txt`'s `python-3.10.14` stay exactly as they are. This bump is required and was verified: `scikit-learn` (a `relbench` dependency) pulls numpy 2.x, and pandas 1.5.2's compiled extensions cannot load against numpy 2, failing at `import pandas` with `ValueError: numpy.dtype size changed`. Pinning `numpy<2` resolves it. The pickle reproduction in plan 1 was already verified against numpy 1.26.4, so this is a bump toward the version the data was checked with, not away from it.
- **The dashboard must never import torch, relbench or torch_geometric.** Predictions reach it as rows in Postgres. `tests/test_no_torch_in_app.py` holds that line.
- **RelBench requires consecutive integer primary keys.** `Dataset.validate_and_correct_db` raises `RuntimeError` unless every table's primary key is exactly `0..n-1` in row order, and it treats foreign keys as integer positions, nulling any value `>= len(pkey_table)`. Our keys are strings (`author_id`, `edition_id`) and a non-contiguous int (`metric_id`), so reindexing is mandatory and is Task 2. **Reindex once, before generating any task labels**, so entity ids align.
- **Time splits are fixed for every task:** `val_timestamp: 2022-12-31`, `test_timestamp: 2023-12-31`. Training sees editions up to and including 2022, validation predicts 2023, test predicts 2024. `timedelta` is `365 days`. Every task uses these, so results are comparable across tasks.
- **Leakage is prevented by `remove_columns`, and it is not optional.** A task whose label is or derives from a database column must name that column in its manifest, as `[table, col]` pairs. `Dataset.get_db` drops them from the graph. Getting this wrong produces a beautiful, meaningless score.
- **Every reported number is accompanied by a trivial baseline.** Majority class for binary tasks, previous-edition value for regression, most-frequent-destination for recommendation. A model that does not beat its baseline is reported as not beating its baseline.
- **`data_rdl/` is gitignored**, like the other data directories. It is regenerable from `data_parquet/`.

---

### Task 1: Bump numpy, create `rdl/`, and prove the dashboard survives

**Files:**
- Modify: `requirements.txt`
- Create: `rdl/__init__.py`, `rdl/spec.py`
- Modify: `.gitignore`
- Test: `rdl/tests/test_spec.py`, `tests/test_no_torch_in_app.py`

**Interfaces:**
- Produces:
  - `rdl.spec.TABLES: dict[str, TableSpec]` where `TableSpec` carries `pkey`, `time_col`, `fkeys: dict[str, str]`, `drop_columns: list[str]`, `stypes: dict[str, str]`. This is deliberately shaped like `relbench.manifest.TableSpec` plus the two things it does not model.
  - `rdl.spec.VAL_TIMESTAMP`, `rdl.spec.TEST_TIMESTAMP`, `rdl.spec.TIMEDELTA`.

- [ ] **Step 1: Write the failing test**

```python
# rdl/tests/test_spec.py
from rdl import spec


def test_career_metrics_is_the_fact_table():
    t = spec.TABLES["career_metrics"]
    assert t.pkey == "metric_id"
    assert t.time_col == "observation_date"
    assert t.fkeys["author_id"] == "authors"
    assert t.fkeys["institution_id"] == "institutions"
    assert t.fkeys["edition_id"] == "editions"


def test_ns_columns_are_dropped():
    """Fifteen non-self-citation restatements of the main metrics. They
    correlate almost perfectly with their bare counterparts."""
    t = spec.TABLES["career_metrics"]
    assert len([c for c in t.drop_columns if c.endswith("_ns")]) == 15


def test_retraction_columns_survive_the_drops():
    """nc_rw is the centrepiece target. Dropping it here would be silent."""
    t = spec.TABLES["career_metrics"]
    for col in ("np_rw", "nc_rw", "nc_to_rw"):
        assert col not in t.drop_columns


def test_provenance_columns_are_dropped_from_editions():
    """sha256 and source_filename have one distinct value per row. They are
    provenance for humans and pure noise to a model."""
    t = spec.TABLES["editions"]
    assert "sha256" in t.drop_columns
    assert "source_filename" in t.drop_columns


def test_splits_are_the_edition_boundaries():
    assert str(spec.VAL_TIMESTAMP) == "2022-12-31"
    assert str(spec.TEST_TIMESTAMP) == "2023-12-31"


def test_every_fkey_target_is_a_declared_table():
    for name, t in spec.TABLES.items():
        for col, dest in t.fkeys.items():
            assert dest in spec.TABLES, f"{name}.{col} -> {dest}"
```

```python
# tests/test_no_torch_in_app.py
import subprocess
import sys


def test_dashboard_import_pulls_in_no_ml_stack():
    """The dashboard reads predictions from Postgres. If torch ever appears
    in its import graph, a 2 GB dependency has leaked into the web process."""
    code = (
        "import app, sys;"
        "bad=[m for m in ('torch','relbench','torch_geometric','torch_frame')"
        " if m in sys.modules];"
        "assert not bad, bad;"
        "print('clean')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest rdl/tests/test_spec.py tests/test_no_torch_in_app.py -v`
Expected: FAIL, no module `rdl.spec`. The torch test should already pass, which is the point: it is a regression guard, written before the dependency exists.

- [ ] **Step 3: Bump numpy and install**

In `requirements.txt`, change exactly one line:

```
numpy==1.21.5     ->     numpy==1.26.4
```

Then add the modelling stack:

```
relbench==3.0.1
pytorch_frame[full]==0.3.0
torch_geometric==2.8.0
torch==2.14.0
duckdb
pyyaml
```

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/pip check
```

**If pip moves pandas or pyarrow, stop and report it.** Verified behaviour is that it does not.

- [ ] **Step 4: Prove the dashboard still works on the new numpy**

This is the gate for the whole plan. Run the existing suite before writing any new code:

```bash
.venv/bin/pytest tests/ -v
```

Expected: all 118 pass. If any fail, the failure is about numpy 1.21 to 1.26 and must be understood and fixed before continuing, not worked around. Record the run in the task report.

Also confirm MPS, since every later task depends on it:

```bash
.venv/bin/python -c "
import torch
print('torch', torch.__version__, 'mps', torch.backends.mps.is_available())
"
```

Expected: `mps True`.

- [ ] **Step 5: Write `rdl/spec.py`**

Reuse the semantic decisions already made and justified: drop the fifteen `_ns` columns, drop the per-row-unique provenance columns from `editions`, pin `firstyr` and `lastyr` as numerical so their low cardinality is not mistaken for a category, treat `inst_name` as text rather than a 66,079-way category.

```python
"""What each table means, relationally and semantically.

This is the single source of truth for both the RelBench manifest and the
stype dictionary. It is shaped like relbench.manifest.TableSpec (pkey,
time_col, fkeys) plus the two things that dataclass does not model: the
columns we drop, and the semantic types we pin rather than let be inferred.

Only the career editions are here. Every task in this plan asks a career
question, and singleyr_metrics is a second 1.2 GB table that answers none of
them. author_name_observations is likewise out: it is the name history, which
matters to entity resolution, a question deferred out of this plan.
"""
from dataclasses import dataclass, field

import pandas as pd

VAL_TIMESTAMP = pd.Timestamp("2022-12-31")
TEST_TIMESTAMP = pd.Timestamp("2023-12-31")
TIMEDELTA = "365 days"

NS_COLUMNS = [
    "rank_ns", "c_ns", "h_ns", "hm_ns", "nc_ns", "nps_ns", "ncs_ns",
    "cpsf_ns", "ncsf_ns", "npsfl_ns", "ncsfl_ns", "npciting_ns",
    "cprat_ns", "np_cited_ns", "rank_subfield_ns",
]


@dataclass(frozen=True)
class TableSpec:
    pkey: str | None = None
    time_col: str | None = None
    fkeys: dict[str, str] = field(default_factory=dict)
    drop_columns: list[str] = field(default_factory=list)
    stypes: dict[str, str] = field(default_factory=dict)


TABLES: dict[str, TableSpec] = {
    "career_metrics": TableSpec(
        pkey="metric_id",
        time_col="observation_date",
        fkeys={
            "author_id": "authors",
            "edition_id": "editions",
            "institution_id": "institutions",
            "field_id": "fields",
            "subfield_1_id": "subfields",
            "subfield_2_id": "subfields",
            "country_code": "countries",
        },
        drop_columns=list(NS_COLUMNS),
        stypes={
            "rank": "numerical", "c": "numerical", "h": "numerical",
            "hm": "numerical", "nc": "numerical", "np": "numerical",
            "firstyr": "numerical", "lastyr": "numerical",
            "rank_subfield": "numerical", "subfield_count": "numerical",
            "np_rw": "numerical", "nc_rw": "numerical",
            "nc_to_rw": "numerical",
            "field_frac": "numerical",
            "subfield_1_frac": "numerical", "subfield_2_frac": "numerical",
            "observation_date": "timestamp",
        },
    ),
    "authors": TableSpec(
        pkey="author_id",
        stypes={
            "authfull_display": "text", "name_normalized": "text",
            "surname": "categorical", "first_initial": "categorical",
            "firstyr": "numerical", "collision_group_size": "numerical",
            "is_ambiguous": "categorical",
            "first_data_year": "numerical", "last_data_year": "numerical",
        },
    ),
    "institutions": TableSpec(
        pkey="institution_id",
        fkeys={"country_code": "countries"},
        # 66,079 distinct names: too high a cardinality for a category, but
        # as text the words carry real signal.
        stypes={"inst_name": "text", "country_code": "categorical"},
    ),
    "editions": TableSpec(
        pkey="edition_id",
        time_col="observation_date",
        drop_columns=["sha256", "source_filename", "columns_present"],
        stypes={
            "mendeley_version": "numerical", "data_year": "numerical",
            "kind": "categorical", "observation_date": "timestamp",
            "published_date": "timestamp",
        },
    ),
    "countries": TableSpec(pkey="country_code"),
    "fields": TableSpec(pkey="field_id"),
    "subfields": TableSpec(pkey="subfield_id"),
}
```

Confirm the dimension tables' real column names before finalising their
`stypes`, rather than assuming `country_name`, `field_name`, `subfield_id`:

```bash
.venv/bin/python -c "
import pyarrow.parquet as pq
for t in ('countries','fields','subfields'):
    print(t, pq.ParquetFile(f'data_parquet/{t}.parquet').schema_arrow.names)
"
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest rdl/tests/test_spec.py tests/test_no_torch_in_app.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
echo "data_rdl/" >> .gitignore
git add rdl/ tests/test_no_torch_in_app.py requirements.txt .gitignore
git commit -m "rdl: bump numpy to 1.26.4 and declare the table semantics"
```

---

### Task 2: Reindex to consecutive integer keys and write the dataset directory

RelBench's contract is strict and checked: `validate_and_correct_db` raises unless every primary key is `0..n-1` in row order, and it silently nulls any foreign key `>= len(pkey_table)`. Our `author_id` and `edition_id` are strings and `metric_id` is a non-contiguous integer, so all of them must be remapped. Doing this before any task labels exist is what keeps entity ids aligned.

**Files:**
- Create: `rdl/build_dataset.py`
- Test: `rdl/tests/test_build_dataset.py`

**Interfaces:**
- Consumes: `data_parquet/*.parquet`, `rdl.spec.TABLES`.
- Produces:
  - `data_rdl/twopercenters/manifest.yaml`
  - `data_rdl/twopercenters/db/<table>.parquet`, every key a consecutive integer
  - `data_rdl/twopercenters/keymap/<table>.parquet`, mapping original key to new integer, so predictions can be joined back to real authors
  - `rdl.build_dataset.reindex(frames: dict) -> tuple[dict, dict]` returning reindexed frames and the key maps.

- [ ] **Step 1: Write the failing test**

```python
# rdl/tests/test_build_dataset.py
import pandas as pd
import pytest

from rdl import build_dataset


def _toy():
    return {
        "authors": pd.DataFrame({
            "author_id": ["z-9", "a-1", "m-5"],
            "surname": ["zed", "ada", "moe"],
        }),
        "career_metrics": pd.DataFrame({
            "metric_id": [500, 100, 900, 700],
            "author_id": ["a-1", "z-9", "a-1", "ghost"],
            "observation_date": pd.to_datetime(
                ["2019-12-31", "2019-12-31", "2020-12-31", "2020-12-31"]),
        }),
    }


def test_primary_keys_become_zero_to_n_minus_one():
    out, _ = build_dataset.reindex(_toy())
    for name, df in out.items():
        pkey = build_dataset.PKEY[name]
        assert list(df[pkey]) == list(range(len(df))), name


def test_foreign_keys_point_at_the_new_positions():
    out, keymap = build_dataset.reindex(_toy())
    authors, metrics = out["authors"], out["career_metrics"]
    lookup = dict(zip(keymap["authors"]["original"],
                      keymap["authors"]["index"]))
    # every non-null fkey resolves to the right author row
    for _, row in metrics.dropna(subset=["author_id"]).iterrows():
        assert authors.loc[int(row["author_id"]), "author_id"] == row["author_id"]
    assert lookup["a-1"] in set(metrics["author_id"].dropna())


def test_dangling_foreign_keys_become_null_not_zero():
    """'ghost' is not an author. Mapping it to 0 would silently attribute
    those rows to whoever sorts first, which is the worst possible failure."""
    out, _ = build_dataset.reindex(_toy())
    assert out["career_metrics"]["author_id"].isna().sum() == 1


def test_fact_rows_are_time_sorted_before_indexing():
    """RelBench indexes in row order, so row order must be meaningful.
    Time order makes the index monotonic in time, which keeps the split
    boundaries contiguous."""
    out, _ = build_dataset.reindex(_toy())
    dates = out["career_metrics"]["observation_date"]
    assert dates.is_monotonic_increasing


def test_keymap_round_trips():
    out, keymap = build_dataset.reindex(_toy())
    km = keymap["authors"].set_index("index")["original"]
    for i, original in km.items():
        assert out["authors"].loc[i, "author_id"] == original
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest rdl/tests/test_build_dataset.py -v`
Expected: FAIL, no module `rdl.build_dataset`.

- [ ] **Step 3: Write `rdl/build_dataset.py`**

Three rules that the tests above encode and that are easy to get wrong:

1. Sort fact tables by their time column **before** assigning indices, so the integer key is monotonic in time.
2. Map dangling foreign keys to `None`, never to `0`. RelBench nulls out-of-range keys itself, but a string key that simply is not in the dimension table would otherwise be silently dropped or, worse, mapped to a real row.
3. Write a key map per table. Without it, a prediction for entity `4471` cannot be turned back into a person's name, which is the whole point of showing it in the dashboard.

The dataset manifest is built with `relbench.manifest.DatasetManifest` and `TableSpec` rather than by hand, so the schema stays correct as the library moves:

```python
from relbench.manifest import DatasetManifest, TableSpec as RBTableSpec

manifest = DatasetManifest(
    name="twopercenters",
    description=(
        "Ioannidis/Elsevier top-2% of scientists, career editions 2017-2024, "
        "normalised from the published spreadsheets."
    ),
    val_timestamp=str(spec.VAL_TIMESTAMP.date()),
    test_timestamp=str(spec.TEST_TIMESTAMP.date()),
    tables={
        name: RBTableSpec(pkey=t.pkey, time_col=t.time_col, fkeys=t.fkeys)
        for name, t in spec.TABLES.items()
    },
)
manifest.save(out_dir / "manifest.yaml")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest rdl/tests/test_build_dataset.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Build the real dataset and check RelBench accepts it**

```bash
.venv/bin/python -m rdl.build_dataset
.venv/bin/python -c "
from relbench.base import Dataset
from rdl.dataset import TwoPercentersDataset
db = TwoPercentersDataset().get_db()
print({k: len(v) for k, v in db.table_dict.items()})
"
```

Expected: no `RuntimeError` about consecutive indexing, and row counts matching plan 1: `career_metrics` 1,402,942, `authors` 818,667, `institutions` 66,079, `editions` 8 career rows once singleyr is excluded.

**Report how many foreign keys were nulled as dangling.** Plan 1 measured 22,327 career rows with no institution and 33,370 with no country, both matching empty cells in the source spreadsheets. Anything beyond those is new and needs explaining before proceeding.

- [ ] **Step 6: Commit**

```bash
git add rdl/build_dataset.py rdl/dataset.py rdl/tests/test_build_dataset.py
git commit -m "rdl: reindex to consecutive keys and emit the RelBench dataset"
```

---

### Task 3: Materialize the graph and measure what it costs

**Files:**
- Create: `rdl/graph.py`
- Test: `rdl/tests/test_graph.py`

**Interfaces:**
- Produces: `rdl.graph.build(cache_dir: str | None) -> tuple[HeteroData, dict]` wrapping `make_pkey_fkey_graph`, and `rdl.graph.stype_dict(db) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# rdl/tests/test_graph.py
from rdl import graph, spec


def test_pinned_stypes_override_the_proposal():
    """get_stype_proposal infers from cardinality, which mislabels firstyr
    (a year, low cardinality) as categorical and would turn a regression
    into a 60-way classification."""
    proposed = {"career_metrics": {"firstyr": "categorical",
                                   "c": "numerical"}}
    merged = graph.apply_pins(proposed)
    assert str(merged["career_metrics"]["firstyr"]) == "numerical"


def test_dropped_columns_never_reach_the_graph():
    proposed = {"career_metrics": {c: "numerical"
                                   for c in spec.NS_COLUMNS + ["c"]}}
    merged = graph.apply_pins(proposed)
    assert not [c for c in merged["career_metrics"] if c.endswith("_ns")]
    assert "c" in merged["career_metrics"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest rdl/tests/test_graph.py -v`
Expected: FAIL, no module `rdl.graph`.

- [ ] **Step 3: Write `rdl/graph.py`**

Start from `relbench.modeling.utils.get_stype_proposal(db)`, then override with the pins from `rdl.spec` and delete the dropped columns. Pass a `cache_dir`, because materialization is slow and every later task repeats it. Text columns (`authfull_display`, `inst_name`) need a `TextEmbedderConfig`; use a small sentence-transformer on CPU and cache the embeddings, since they are computed once and reused.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest rdl/tests/test_graph.py -v`
Expected: PASS.

- [ ] **Step 5: Build the graph and record the numbers**

```bash
.venv/bin/python -m rdl.graph --cache data_rdl/cache
```

Report node and edge counts per type, wall-clock time, and peak RSS. Plan 1 measured the tables at roughly 1,430 MB in pandas; the graph adds the encoded feature tensors on top. **This machine has 24 GB, so if peak RSS approaches 16 GB, say so** and narrow before training rather than discovering it mid-epoch.

- [ ] **Step 6: Commit**

```bash
git add rdl/graph.py rdl/tests/test_graph.py
git commit -m "rdl: build the heterogeneous graph with pinned semantic types"
```

---

### Task 4: The training harness, once, for every task

Writing this once is the difference between four tasks and four copies of a training loop.

**Files:**
- Create: `rdl/model.py`, `rdl/train.py`
- Test: `rdl/tests/test_train.py`

**Interfaces:**
- Produces:
  - `rdl.model.Model(data, col_stats_dict, task_type, out_channels, ...)` wrapping `HeteroEncoder`, `HeteroTemporalEncoder` and `HeteroGraphSAGE` from `relbench.modeling.nn`.
  - `rdl.train.run(task_name: str, epochs: int, device: str) -> dict` returning metrics for train, val and test, and writing predictions to `data_rdl/predictions/<task>.parquet`.
  - `rdl.train.pick_device() -> str`.

- [ ] **Step 1: Write the failing test**

```python
# rdl/tests/test_train.py
import pytest
import torch

from rdl import train


def test_pick_device_prefers_mps_when_available(monkeypatch):
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
    assert train.pick_device() == "mps"


def test_pick_device_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert train.pick_device() == "cpu"


def test_baseline_majority_class():
    import numpy as np
    y = np.array([1, 1, 1, 0])
    assert train.majority_baseline(y) == pytest.approx(0.75)


def test_baseline_is_reported_alongside_every_metric():
    """A score with no baseline beside it is not a result."""
    out = train.format_result({"roc_auc": 0.81}, {"roc_auc": 0.50})
    assert "baseline" in out
    assert out["baseline"]["roc_auc"] == 0.50
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest rdl/tests/test_train.py -v`
Expected: FAIL, no module `rdl.train`.

- [ ] **Step 3: Write the model and the loop**

Follow RelBench's reference architecture rather than inventing one: `HeteroEncoder` encodes each table's `TensorFrame`, `HeteroTemporalEncoder` adds the relative-time signal, `HeteroGraphSAGE` does the message passing, and a small head maps the entity node's embedding to the task output. Use `NeighborLoader` over the seed nodes from `get_node_train_table_input`.

Device notes for this machine, verified: MPS is available and correct for heterogeneous message passing, measured at 69 ms/step against 81 ms on CPU for a 600k-node, 800k-edge layer. That is only about 1.2x, because at this size the work is memory-bandwidth bound, so **CPU is a legitimate fallback and not a failure state**. Set `num_workers=0` on MPS; worker processes and MPS tensors do not mix.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest rdl/tests/test_train.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add rdl/model.py rdl/train.py rdl/tests/test_train.py
git commit -m "rdl: the shared model and training loop, MPS-aware"
```

---

### Task 5: Retraction exposure, the centrepiece

This is the task the dataset is unusually good for, and RelBench has a task kind built for exactly its shape. The three retraction columns arrived with Mendeley version 7: `career-2017` through `career-2022` are 100% NULL for all of them, `career-2023` and `career-2024` are 0% NULL. The label **is** a database column, which is RelBench's `autocomplete` kind, so no label-generating SQL is needed.

The column choice was settled by measurement and matters:

| Column | Meaning | 2023 nonzero | 2024 nonzero |
|---|---|---|---|
| `np_rw` | the author's own retracted papers | 3.26% | 3.82% |
| `nc_to_rw` | cites to this author's retracted papers | 3.01% | 3.54% |
| `nc_rw` | cites received from any retracted paper | **71.12%** | **75.95%** |

`np_rw` is 96.7% zero, so a regression on it scores well by predicting zero for everyone. `nc_rw` is the target.

**Files:**
- Create: `data_rdl/twopercenters/tasks/retraction_exposure/manifest.yaml`
- Create: `rdl/tasks/retraction.py`
- Test: `rdl/tests/test_retraction_task.py`

- [ ] **Step 1: Write the failing test**

```python
# rdl/tests/test_retraction_task.py
import pandas as pd
import pytest

from rdl.tasks import retraction


def test_all_three_retraction_columns_are_removed_not_just_the_target():
    """nc_rw is the label, but np_rw and nc_to_rw are the same measurement
    from the same source. Leaving either in the graph leaks the answer."""
    removed = {tuple(pair) for pair in retraction.MANIFEST["remove_columns"]}
    assert ("career_metrics", "nc_rw") in removed
    assert ("career_metrics", "np_rw") in removed
    assert ("career_metrics", "nc_to_rw") in removed


def test_it_is_an_autocomplete_task():
    """The label is a database column, not something derived over a future
    window, so this is autocomplete rather than forecast."""
    assert retraction.MANIFEST["kind"] == "autocomplete"
    assert retraction.MANIFEST["entity_table"] == "career_metrics"
    assert retraction.MANIFEST["entity_col"] == "metric_id"
    assert retraction.MANIFEST["target_col"] == "nc_rw"


def test_labelled_rows_are_only_the_two_tracked_editions():
    df = pd.read_parquet("data_parquet/career_metrics.parquet",
                         columns=["edition_id", "nc_rw"])
    labelled = set(df.loc[df["nc_rw"].notna(), "edition_id"].unique())
    assert labelled == {"career-2023", "career-2024"}


def test_the_unlabelled_count_is_what_we_measured():
    df = pd.read_parquet("data_parquet/career_metrics.parquet",
                         columns=["nc_rw"])
    assert int(df["nc_rw"].isna().sum()) == 955512
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest rdl/tests/test_retraction_task.py -v`
Expected: FAIL, no module `rdl.tasks.retraction`. The two data tests should pass immediately; they are guards on facts plan 1 established.

- [ ] **Step 3: Write the task manifest**

```yaml
# data_rdl/twopercenters/tasks/retraction_exposure/manifest.yaml
name: retraction_exposure
kind: autocomplete
task_type: regression
description: >
  Impute cites-received-from-retracted-papers for the six career editions
  published before retraction tracking began. Labels exist only for 2023 and
  2024; 955,512 rows across 2017-2022 have none.
entity_table: career_metrics
entity_col: metric_id
target_col: nc_rw
time_col: observation_date
remove_columns:
  - [career_metrics, nc_rw]
  - [career_metrics, np_rw]
  - [career_metrics, nc_to_rw]
```

A second manifest, `retraction_exposed`, is identical except `task_type: binary_classification` on `nc_rw > 0`, which gives a ROC AUC that means something rather than a regression error dominated by a long tail. A third, `own_retractions`, targets `np_rw > 0` as the deliberately harder rare-event case.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest rdl/tests/test_retraction_task.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Train and evaluate**

```bash
.venv/bin/python -m rdl.train retraction_exposed --epochs 10
.venv/bin/python -m rdl.train retraction_exposure --epochs 10
.venv/bin/python -m rdl.train own_retractions --epochs 10
```

**Report all three, including the weak one**, each beside its baseline. Majority class gives roughly 0.71 accuracy on `retraction_exposed` and roughly 0.96 on `own_retractions`, which is precisely why accuracy is the wrong metric for these and ROC AUC is quoted instead. An audience of relational-learning people will check this, and reporting only the flattering task is the fastest way to lose them.

- [ ] **Step 6: Impute the six untracked years**

Run inference over all 955,512 unlabelled rows and write `data_rdl/predictions/retraction_exposure.parquet`, joined back to real `author_id` values through the key map. This is the output nobody currently has, and it is the thing worth showing.

- [ ] **Step 7: Commit**

```bash
git add rdl/tasks/retraction.py rdl/tests/test_retraction_task.py data_rdl/twopercenters/tasks/
git commit -m "rdl: retraction exposure imputation, validated on 2023-2024"
```

---

### Task 6: The three forecast tasks

These are `kind: forecast`, so each carries a duckdb SQL query that regenerates labels from the database. The SQL sees a `timestamps(timestamp)` relation holding the per-split seed timestamps, every table as a view, and `{timedelta}` substituted as an INTERVAL. Its SELECT must output the declared entity, target and time columns.

**Files:**
- Create: three task manifests under `data_rdl/twopercenters/tasks/`
- Create: `rdl/tasks/forecast.py`
- Test: `rdl/tests/test_forecast_tasks.py`

- [ ] **Step 1: Write the failing test**

```python
# rdl/tests/test_forecast_tasks.py
from rdl.tasks import forecast


def test_dropout_is_binary_over_the_next_edition():
    m = forecast.DROPOUT
    assert m["kind"] == "forecast"
    assert m["task_type"] == "binary_classification"
    assert m["entity_table"] == "authors"
    assert m["timedelta"] == "365 days"


def test_every_forecast_task_has_sql():
    for m in forecast.ALL:
        assert m["sql"], m["name"]
        assert "timestamps" in m["sql"], m["name"]


def test_next_affiliation_is_a_recommendation_over_institutions():
    m = forecast.NEXT_AFFILIATION
    assert m["task_type"] == "recommendation"
    assert m["src_entity_table"] == "authors"
    assert m["dst_entity_table"] == "institutions"
    assert 1 <= m["eval_k"] <= 20


def test_next_score_removes_nothing_because_c_is_a_future_value():
    """c at the next edition is a different row, not this row's column, so
    no column needs removing. Stated explicitly because the reflex is to
    add one."""
    assert forecast.NEXT_SCORE["remove_columns"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest rdl/tests/test_forecast_tasks.py -v`
Expected: FAIL, no module `rdl.tasks.forecast`.

- [ ] **Step 3: Write the three manifests**

**Dropout**, the competitive one: staying on the list is a threshold on rank within a subfield, so an author can do everything right and still fall off because others did better.

```sql
SELECT t.timestamp AS observation_date,
       a.author_id  AS author_id,
       CASE WHEN COUNT(m.metric_id) = 0 THEN 1 ELSE 0 END AS dropped_out
FROM timestamps t
CROSS JOIN authors a
LEFT JOIN career_metrics m
       ON m.author_id = a.author_id
      AND m.observation_date >  t.timestamp
      AND m.observation_date <= t.timestamp + INTERVAL {timedelta}
WHERE EXISTS (SELECT 1 FROM career_metrics p
               WHERE p.author_id = a.author_id
                 AND p.observation_date <= t.timestamp)
GROUP BY t.timestamp, a.author_id
```

The `EXISTS` clause is load-bearing: without it every author who had not yet appeared counts as a dropout, and the task becomes "predict whether this person has published yet", which is both trivial and wrong.

**Next-edition score**, regression on `c`. Include it, and be honest about it: career metrics are cumulative since 1960, so next year's `c` is nearly this year's `c`. The previous-edition baseline is expected to be very strong, and if the model merely matches it, that is the finding.

**Next affiliation**, recommendation with `src_entity_table: authors`, `dst_entity_table: institutions`, `eval_k: 10`. Genuinely hard: affiliation is itself Scopus's ML guess at one of several, and plan 1 measured it only 69 to 84 percent stable year over year.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest rdl/tests/test_forecast_tasks.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Check the label distributions before training anything**

```bash
.venv/bin/python -m rdl.tasks.forecast --stats
```

`EntityTask.stats()` reports positives and negatives per split for binary tasks and quantiles for regression. **Read this before training.** A dropout rate near zero or near one means the task is mis-specified, and finding that after a training run wastes an hour.

- [ ] **Step 6: Train all three and report against baselines**

```bash
for t in dropout next_score next_affiliation; do
  .venv/bin/python -m rdl.train $t --epochs 10
done
```

Baselines: majority class for dropout, previous-edition `c` for next score, most-frequent-institution and same-institution-as-last-year for next affiliation. The last of those is the one to beat, and it will be strong.

- [ ] **Step 7: Commit**

```bash
git add rdl/tasks/forecast.py rdl/tests/test_forecast_tasks.py data_rdl/twopercenters/tasks/
git commit -m "rdl: dropout, next score and next affiliation forecast tasks"
```

---

### Task 7: OpenAlex co-authorship enrichment

Without this, every path between two authors runs through an institution or a field, which is thin relational context. Co-authorship turns the star schema into a network, which is the setting where relational deep learning has an argument to make. It is also the only external anchor available for checking our identity resolution.

The full OpenAlex snapshot is hundreds of gigabytes and out of proportion here. **Link a stratified 20,000-author sample through the API**, respecting the February 2026 change that requires a free key with a daily allowance. Cache every response on disk so reruns cost nothing against the allowance.

**Files:**
- Create: `rdl/openalex/fetch.py`, `rdl/openalex/link.py`
- Test: `rdl/tests/test_openalex_link.py`

- [ ] **Step 1: Write the failing test**

```python
# rdl/tests/test_openalex_link.py
from rdl.openalex import link


def test_name_form_is_inverted_for_the_query():
    """Scopus publishes 'Surname, Given'; OpenAlex indexes 'Given Surname'.
    Searching the raw Scopus string finds nothing."""
    assert link.to_query_form("Ioannidis, John P.A.") == "John P.A. Ioannidis"


def test_compound_surnames_survive():
    """Split on the comma first, then strip. Normalising first removes the
    comma, which is exactly the bug that broke block_key in plan 1."""
    assert link.to_query_form("van der Berg, Jan") == "Jan van der Berg"


def test_a_name_without_a_comma_passes_through():
    assert link.to_query_form("Madonna") == "Madonna"


def test_an_orcid_match_outranks_a_bare_name_match():
    with_orcid = {"orcid": "0000-0001", "display_name": "Jan van der Berg"}
    without = {"orcid": None, "display_name": "Jan van der Berg"}
    assert (link.score("van der Berg, Jan", with_orcid)
            > link.score("van der Berg, Jan", without))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest rdl/tests/test_openalex_link.py -v`
Expected: FAIL, no module `rdl.openalex`.

- [ ] **Step 3: Implement the fetch and the linkage**

Read the key from `OPENALEX_API_KEY` and always send a mailto, which is the documented polite-pool convention. Cache by query on disk. Retry three times with backoff. Score matches simply and explainably: exact normalised name match, plus a bonus for an ORCID, plus a bonus for a plausible works count. An ORCID is worth a lot, because it means OpenAlex has an externally anchored identity rather than only its own clustering.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest rdl/tests/test_openalex_link.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Link the sample and add the edges**

Stratify the 20,000 by `is_ambiguous` and by whether the author appears on both sides of the 2023-2024 boundary, so the sample is informative rather than merely large. Add `openalex_authors` and `coauthorship` tables to the dataset directory and rebuild.

**Report the linkage rate and the score distribution.** A low rate is a finding about how hard author disambiguation is, not a failure to bury. If the daily allowance runs out, record how far it got; the cache makes resuming free.

- [ ] **Step 6: Re-run the tasks with the enriched graph and compare**

This is the measurement that justifies the whole task. Re-run `retraction_exposed` and `dropout` on the enriched graph and put the numbers beside the Task 5 and Task 6 results. **If co-authorship does not help, report that it does not help.** It is a real result about this dataset either way, and on a 20,000-author sample against 818,667 authors, a null result would be unsurprising and worth stating.

- [ ] **Step 7: Commit**

```bash
git add rdl/openalex/ rdl/tests/test_openalex_link.py
git commit -m "rdl: OpenAlex co-authorship edges for a stratified sample"
```

---

### Task 8: Put the predictions in the dashboard

Predictions are computed in batch and stored in Postgres. The dashboard reads a table. It does not import torch, and `tests/test_no_torch_in_app.py` from Task 1 enforces that.

**Files:**
- Create: `db/migrations/008_predictions.sql`
- Create: `rdl/publish.py`
- Create: `pages/predictions.py`
- Test: `rdl/tests/test_publish.py`, `tests/test_predictions_page.py`

- [ ] **Step 1: Write the failing test**

```python
# rdl/tests/test_publish.py
import pandas as pd
import pytest

from rdl import publish


def test_predictions_are_joined_back_to_real_author_ids():
    """A prediction for entity 4471 is meaningless to a reader. The key map
    is what turns it back into a person."""
    preds = pd.DataFrame({"entity": [0, 1], "pred": [3.5, 0.0]})
    keymap = pd.DataFrame({"index": [0, 1], "original": ["a-1", "z-9"]})
    out = publish.attach_ids(preds, keymap)
    assert list(out["author_id"]) == ["a-1", "z-9"]


def test_publishing_refuses_a_task_with_no_recorded_metrics():
    """A number on a dashboard with no evaluation behind it is worse than
    no number."""
    with pytest.raises(ValueError, match="metrics"):
        publish.validate({"task": "dropout", "metrics": {}})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest rdl/tests/test_publish.py -v`
Expected: FAIL, no module `rdl.publish`.

- [ ] **Step 3: Write the migration**

`008_predictions.sql` creates `predictions(task text, author_id text, metric_id bigint, value double precision, probability double precision, edition_id text)` and `prediction_runs(task text primary key, task_type text, trained_at timestamptz, epochs int, metrics jsonb, baseline jsonb, graph_variant text)`.

`graph_variant` distinguishes the core graph from the OpenAlex-enriched one, so Task 7's comparison survives into the dashboard instead of living only in a report.

Follow plan 1's conventions: numbered SQL, applied once by `db/migrate.py` in sorted filename order.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest rdl/tests/test_publish.py -v`
Expected: PASS.

- [ ] **Step 5: Add the page**

`pages/predictions.py` shows, per task: the question in plain words, the metric, **the baseline beside it**, the training date, and the graph variant. For retraction exposure it shows the imputed six years as a chart alongside the two known years, with the known years visually distinct from the imputed ones. A reader must never be unable to tell which is measured and which is predicted.

Two hazards from plan 1 apply directly: do not query the database at module import, which is what forced `close_db()` in `app.py` and the `post_fork` hook in `cfg.py`; and do not register the page at a guessable scratch route, which `pages/test.py` at `/keke` still does.

- [ ] **Step 6: Run the full suite**

```bash
.venv/bin/pytest tests/ -v
.venv/bin/pytest rdl/tests/ -v
```

Expected: the dashboard's 118 tests plus the new page test, all green, and `test_no_torch_in_app` still passing with the ML stack installed. That last one is the real check of this task.

- [ ] **Step 7: Commit**

```bash
git add db/migrations/008_predictions.sql rdl/publish.py pages/predictions.py rdl/tests/test_publish.py tests/test_predictions_page.py
git commit -m "rdl: publish predictions to Postgres and show them with baselines"
```

---

## What this plan does not do

- **Entity resolution as link prediction.** It needs a candidate-pair table built by blocking, and it deserves its own plan. The deterministic 85.2% baseline from plan 1 stands until then, reported as a linkage rate rather than as precision.
- **`singleyr_metrics` in the graph.** No task here asks a single-year question, and it is a second 1.2 GB table.
- **Deploying the ML stack to dokku.** Only the `predictions` table ships. Training happens on this machine.
- **The OpenAlex bulk snapshot.** Task 7 links a stratified 20,000-author sample through the API.
- **Hyperparameter search.** Every task runs the reference architecture at a fixed configuration. Tuning comes after there is something worth tuning.

## Open questions this plan will answer

1. Do the 118 dashboard tests pass on numpy 1.26.4? (Task 1)
2. How many foreign keys are dangling once keys are reindexed, and does that match plan 1's measured empties? (Task 2)
3. Does the graph fit comfortably in 24 GB? (Task 3)
4. Can retraction exposure be imputed better than the majority-class baseline, and how much worse is the rare-event variant? (Task 5)
5. Does dropout beat majority class, and does next-affiliation beat same-institution-as-last-year? (Task 6)
6. Does co-authorship enrichment measurably help on a 20,000-author sample? (Task 7)
