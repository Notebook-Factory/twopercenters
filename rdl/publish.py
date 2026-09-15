"""Put the model's estimates where the dashboard can read them.

Training happens offline on a workstation; the web process never imports
torch. The only thing that crosses that line is rows in the `predictions`
table, which is what this writes.

Two rules about those rows.

They are estimates for a quantity that was never measured, and they are
stored apart from anything the publishers reported so that no query can
return one beside a published figure without saying which is which.

They travel with the score the model got on data it never saw, and with the
trivial baseline for the same split. A score on its own is not a result here:
on the dropout task a single flag recording our own resolver's confusion
scored 0.776 against the model's 0.814, and reporting the model alone would
have been reporting an artefact.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PREDICTIONS_DIR = ROOT / "data_rdl" / "predictions"
KEYMAP_DIR = ROOT / "data_rdl" / "twopercenters" / "keymap"

TARGET_COLUMN = {
    "retraction_exposed": "nc_rw",
    "retraction_exposure": "nc_rw",
    "own_retractions": "np_rw",
}


def validate(run: dict) -> None:
    """Refuse to publish a run that cannot say how good it is."""
    if not run.get("metrics"):
        raise ValueError(
            f"{run.get('task')!r} has no metrics: a number on a dashboard "
            "with no evaluation behind it is worse than no number")
    if "baseline" not in run:
        raise ValueError(
            f"{run.get('task')!r} has no baseline. A score without one is "
            "not a result on this data")


def attach_ids(preds: pd.DataFrame, keymap: pd.DataFrame,
               on: str = "author_id") -> pd.DataFrame:
    """Turn integer graph indices back into the identifiers people use."""
    lookup = dict(zip(keymap["index"], keymap["original"]))
    out = preds.copy()
    out[on] = out[on].map(lookup)
    return out


def _run_record(task: str) -> dict:
    payload = json.loads((PREDICTIONS_DIR / f"{task}.json").read_text())
    test = payload["results"]["test"]
    return {
        "task": task,
        "task_type": payload["task_type"].replace("TaskType.", "").lower(),
        "target_column": TARGET_COLUMN.get(task, ""),
        "epochs": payload.get("epochs"),
        "metrics": test["metrics"],
        "baseline": test["baseline"],
    }


def publish(task: str, conn) -> int:
    run = _run_record(task)
    validate(run)

    frame = pd.read_parquet(PREDICTIONS_DIR / f"{task}_backfill.parquet")
    column = "probability" if "probability" in frame.columns else "value"

    if column == "value":
        # The regression head is unconstrained, so it happily predicts a
        # negative count: 40.8% of the retraction_exposure backfill came out
        # below zero. A count of citations cannot be negative, and storing an
        # impossible value invites something downstream to average it. Zero
        # is what a negative prediction means here.
        negatives = int((frame[column] < 0).sum())
        if negatives:
            logger.info("clamping %d negative predictions to zero (%.1f%%)",
                        negatives, 100 * negatives / len(frame))
            frame[column] = frame[column].clip(lower=0)

    conn.execute("""
        insert into prediction_runs (task, task_type, target_column, epochs,
                                     metrics, baseline, graph_variant, notes)
        values (%s, %s, %s, %s, %s, %s, 'core', %s)
        on conflict (task) do update set
            task_type = excluded.task_type,
            target_column = excluded.target_column,
            trained_at = now(),
            epochs = excluded.epochs,
            metrics = excluded.metrics,
            baseline = excluded.baseline,
            notes = excluded.notes
    """, (run["task"], run["task_type"], run["target_column"], run["epochs"],
          json.dumps(run["metrics"]), json.dumps(run["baseline"]),
          "Estimates for editions published before retraction tracking "
          "began. Trained on career-2023, evaluated on the held-out "
          "career-2024 edition."))

    conn.execute("delete from predictions where task = %s", (task,))
    rows = [
        (task, int(r.metric_id), r.author_id, r.edition_id,
         float(getattr(r, column)) if column == "probability" else None,
         float(getattr(r, column)) if column == "value" else None)
        for r in frame.itertuples()
    ]
    with conn.cursor() as cur:
        with cur.copy("copy predictions (task, metric_id, author_id, "
                      "edition_id, probability, value) from stdin") as copy:
            for row in rows:
                copy.write_row(row)
    logger.info("published %d estimates for %s", len(rows), task)
    return len(rows)


def main() -> None:
    from db.connection import connect

    parser = argparse.ArgumentParser()
    parser.add_argument("tasks", nargs="*", default=["retraction_exposed"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with connect() as conn:
        for task in (args.tasks or ["retraction_exposed"]):
            print(f"{task}: {publish(task, conn):,} rows")
        conn.commit()


if __name__ == "__main__":
    main()
