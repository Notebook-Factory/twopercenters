"""Forecast tasks: what happens to this author at the next edition.

These are `kind: forecast`, so each carries a duckdb query that regenerates
its labels from the database. The query sees a ``timestamps(timestamp)``
relation holding the seed timestamps for the split and every table as a view
by name.

The queries are written in terms of **editions**, not day arithmetic, and
that is the whole design. Two measurements forced it.

A fixed-length window cannot track annual editions across leap years. The
editions are stamped 31 December, and 2019-12-31 plus 365 days is 2020-12-30,
one day short of the 2020 edition. With a 365-day window, a label built
from "the next edition" found no next edition for the 2019 and 2023 seeds and
looked entirely plausible for the other four.

Worse, the seed timestamps themselves drift. RelBench builds the training
seeds by stepping back one timedelta at a time from val_timestamp, so with
365 days they run 2021-12-31, 2020-12-31, then 2020-01-01, 2019-01-01 --
off the edition dates entirely, because 2020 is a leap year. Any query that
matched an edition by equality with the seed timestamp would silently match
nothing for most of the training range.

So the label window is "the next edition strictly after this timestamp" and
the population is "the most recent edition at or before it", both expressed
as subqueries. Nothing depends on the interval's length, which leaves
timedelta free to satisfy RelBench's own constraint that it not exceed the
gap between val_timestamp and test_timestamp.

The population choice matters separately. Anchoring to the most recent
edition rather than to every author who ever appeared keeps someone who
appeared once in 2017 from being a seed at every later timestamp.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
TASKS_DIR = ROOT / "data_rdl" / "twopercenters" / "tasks"

# Only controls the spacing of seed timestamps, never the label definition,
# which is expressed in editions. RelBench requires it to be no larger than
# the gap between val_timestamp and test_timestamp, which is 365 days.
TIMEDELTA = "365 days"


NEXT_RANK_SQL = """
SELECT t.timestamp AS observation_date,
       p.author_id  AS author_id,
       MIN(m.rank)  AS next_rank
FROM timestamps t
JOIN career_metrics p
  ON p.observation_date = (
       SELECT MAX(observation_date) FROM career_metrics
       WHERE observation_date <= t.timestamp
     )
JOIN career_metrics m
  ON m.author_id = p.author_id
 AND m.observation_date = (
       SELECT MIN(observation_date) FROM career_metrics
       WHERE observation_date > t.timestamp
     )
GROUP BY t.timestamp, p.author_id
"""

NEXT_SCORE_SQL = """
SELECT t.timestamp AS observation_date,
       p.author_id  AS author_id,
       MIN(m.c)     AS next_c
FROM timestamps t
JOIN career_metrics p
  ON p.observation_date = (
       SELECT MAX(observation_date) FROM career_metrics
       WHERE observation_date <= t.timestamp
     )
JOIN career_metrics m
  ON m.author_id = p.author_id
 AND m.observation_date = (
       SELECT MIN(observation_date) FROM career_metrics
       WHERE observation_date > t.timestamp
     )
GROUP BY t.timestamp, p.author_id
"""


TASKS = {
    "next_rank": {
        "task_type": "regression",
        "target_col": "next_rank",
        "persistence_col": "rank",
        "sql": NEXT_RANK_SQL,
        "description": (
            "The author's overall rank at the next edition, for authors who "
            "appear in it. The baseline to beat is this edition's rank, and "
            "it is a strong one."
        ),
    },
    "next_score": {
        "task_type": "regression",
        "target_col": "next_c",
        "persistence_col": "c",
        "sql": NEXT_SCORE_SQL,
        "description": (
            "The composite score c at the next edition. Included to be "
            "honest about a weak question: c is cumulative since 1960, so "
            "next year's value is nearly this year's, and a good score here "
            "means very little."
        ),
    },
}

# The label is a property of a future row rather than a column of the entity
# row, so nothing needs hiding. Stated explicitly because the reflex, after
# the retraction tasks, is to add a removal.
REMOVE_COLUMNS: list = []

ALL = [dict(name=name, **cfg) for name, cfg in TASKS.items()]


def build_task(name: str, tasks_dir: Path = TASKS_DIR) -> Path:
    cfg = TASKS[name]
    task_dir = tasks_dir / name
    task_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "kind": "forecast",
        "task_type": cfg["task_type"],
        "description": cfg["description"],
        "entity_table": "authors",
        "entity_col": "author_id",
        "target_col": cfg["target_col"],
        "time_col": "observation_date",
        "timedelta": TIMEDELTA,
        "remove_columns": REMOVE_COLUMNS,
        "sql": cfg["sql"].strip(),
    }
    (task_dir / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False))
    return task_dir


def build_all(tasks_dir: Path = TASKS_DIR) -> list[Path]:
    return [build_task(name, tasks_dir) for name in TASKS]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks-dir", default=str(TASKS_DIR))
    parser.add_argument("--stats", action="store_true",
                        help="print each task's label distribution per split")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    for path in build_all(Path(args.tasks_dir)):
        print("wrote", path)

    if args.stats:
        from relbench.load import load_dataset
        dataset = load_dataset(str(ROOT / "data_rdl" / "twopercenters"))
        for name in TASKS:
            task = dataset.load_task(name)
            print(f"\n=== {name} ===")
            for split in ("train", "val", "test"):
                table = task.get_table(split, mask_input_cols=False)
                col = task.target_col
                series = table.df[col]
                if TASKS[name]["task_type"] == "binary_classification":
                    print(f"  {split:5s} n={len(series):7d} "
                          f"positive_rate={series.mean():.4f}")
                else:
                    print(f"  {split:5s} n={len(series):7d} "
                          f"median={series.median():.4f}")


if __name__ == "__main__":
    main()
