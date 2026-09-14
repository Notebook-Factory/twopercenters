"""Retraction exposure: impute what the untracked editions never recorded.

The three retraction columns arrived with Mendeley version 7. career-2017
through career-2022 are 100% NULL for all of them and career-2023 and
career-2024 are 0% NULL, verified: 955,512 unlabelled rows against 447,430
labelled ones. That is a real missing-value problem with its own built-in
validation set.

Which column matters, and it is not the obvious one:

    column      meaning                                2023    2024
    np_rw       the author's own retracted papers      3.26%   3.82% nonzero
    nc_to_rw    cites to this author's retracted work  3.01%   3.54% nonzero
    nc_rw       cites received from any retracted work 71.12%  75.95% nonzero

np_rw is 96.7% zero, so a regression on it scores well by predicting zero for
everyone and demonstrates nothing. nc_rw is the quantity that actually means
"retraction exposure" and it is balanced enough to learn from. It is the
target; np_rw is kept as the deliberately harder rare-event case and reported
as such rather than quietly dropped.

Why these are `external` tasks rather than `autocomplete`
--------------------------------------------------------
An autocomplete task derives its splits from the dataset's global
val_timestamp and test_timestamp, and drops rows whose target is NULL. Every
labelled row in this dataset sits in the last two editions, which fall after
val_timestamp (2022-12-31), so the train split would come out empty. No
choice of global timestamps fixes that: moving them earlier leaves train
still unlabelled, and moving them later empties val. Autocomplete is
structurally wrong for a column that only exists at the end of the history.

External tasks ship their own labels, so the split is ours to choose, and the
one we want is the one that matches the real use: train on career-2023 and
test on career-2024, an entirely different edition. The eventual application
imputes six editions the model has never seen a label for, so measuring
across an edition boundary is the honest proxy. A random split within the two
labelled editions would score better and mean less.
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = Path(os.environ.get("RDL_DATASET_DIR", ROOT / "data_rdl" / "twopercenters"))
DB_DIR = DATASET_DIR / "db"
TASKS_DIR = DATASET_DIR / "tasks"

# All three retraction columns are hidden from the graph for every one of
# these tasks, not just the one being predicted. They are the same
# measurement from the same source arriving in the same edition, so leaving
# either of the other two in leaks the answer.
REMOVE_COLUMNS = [
    ["career_metrics", "np_rw"],
    ["career_metrics", "nc_to_rw"],
    ["career_metrics", "nc_rw"],
]

TRAIN_EDITION = pd.Timestamp("2023-12-31")
TEST_EDITION = pd.Timestamp("2024-12-31")
VAL_FRACTION = 0.1
SEED = 20260914


TASKS = {
    "retraction_exposure": {
        "task_type": "regression",
        "source_col": "nc_rw",
        "target_col": "nc_rw",
        "threshold": None,
        "description": (
            "Impute cites received from retracted papers for the career "
            "editions published before retraction tracking began."
        ),
    },
    "retraction_exposed": {
        "task_type": "binary_classification",
        "source_col": "nc_rw",
        "target_col": "exposed",
        "threshold": 0,
        "description": (
            "Whether an author has any citation exposure to retracted work. "
            "Positive in 71-76% of labelled rows."
        ),
    },
    "own_retractions": {
        "task_type": "binary_classification",
        "source_col": "np_rw",
        "target_col": "has_retraction",
        "threshold": 0,
        "description": (
            "Whether an author has any retracted paper of their own. The "
            "rare-event case: positive in only 3.3-3.8% of labelled rows."
        ),
    },
}

# Kept importable for the tests, which assert on the manifest without
# building it.
MANIFEST = {
    "kind": "external",
    "entity_table": "career_metrics",
    "entity_col": "metric_id",
    "time_col": "observation_date",
    "remove_columns": REMOVE_COLUMNS,
}


def _labels(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    source = cfg["source_col"]
    out = df.loc[df[source].notna(),
                 ["observation_date", "metric_id", source]].copy()
    if cfg["threshold"] is None:
        out = out.rename(columns={source: cfg["target_col"]})
        # float32: MPS has no float64, and this column becomes batch.y.
        out[cfg["target_col"]] = out[cfg["target_col"]].astype("float32")
    else:
        out[cfg["target_col"]] = (
            out[source] > cfg["threshold"]).astype("int64")
        out = out.drop(columns=[source])
    return out


def build_task(name: str, df: pd.DataFrame, tasks_dir: Path = TASKS_DIR) -> dict:
    cfg = TASKS[name]
    labels = _labels(df, cfg)

    train_pool = labels[labels["observation_date"] == TRAIN_EDITION]
    test = labels[labels["observation_date"] == TEST_EDITION]
    if train_pool.empty or test.empty:
        raise ValueError(
            f"{name}: expected labels in both {TRAIN_EDITION.date()} and "
            f"{TEST_EDITION.date()}, got {len(train_pool)} and {len(test)}")

    val = train_pool.sample(frac=VAL_FRACTION, random_state=SEED)
    train = train_pool.drop(index=val.index)

    task_dir = tasks_dir / name
    task_dir.mkdir(parents=True, exist_ok=True)
    for split, frame in (("train", train), ("val", val), ("test", test)):
        frame = frame.sort_values(["observation_date", "metric_id"],
                                  kind="mergesort").reset_index(drop=True)
        frame.to_parquet(task_dir / f"{split}.parquet", index=False)

    manifest = {
        "name": name,
        "kind": "external",
        "task_type": cfg["task_type"],
        "description": cfg["description"],
        "entity_table": "career_metrics",
        "entity_col": "metric_id",
        "target_col": cfg["target_col"],
        "time_col": "observation_date",
        "timedelta": "365 days",
        "remove_columns": REMOVE_COLUMNS,
    }
    (task_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest,
                                                           sort_keys=False))

    stats = {
        "task": name,
        "train": len(train),
        "val": len(val),
        "test": len(test),
    }
    if cfg["threshold"] is not None:
        stats["train_positive_rate"] = round(
            float(train[cfg["target_col"]].mean()), 4)
        stats["test_positive_rate"] = round(
            float(test[cfg["target_col"]].mean()), 4)
    else:
        stats["train_median"] = float(train[cfg["target_col"]].median())
        stats["test_median"] = float(test[cfg["target_col"]].median())
    return stats


def build_all(tasks_dir: Path = TASKS_DIR) -> list[dict]:
    df = pd.read_parquet(
        DB_DIR / "career_metrics.parquet",
        columns=["observation_date", "metric_id", "nc_rw", "np_rw"])
    df["observation_date"] = pd.to_datetime(df["observation_date"])
    return [build_task(name, df, tasks_dir) for name in TASKS]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks-dir", default=str(TASKS_DIR))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for stats in build_all(Path(args.tasks_dir)):
        print(stats)


if __name__ == "__main__":
    main()
