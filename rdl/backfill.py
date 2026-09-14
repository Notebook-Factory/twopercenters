"""Score the rows nobody has an answer for.

This is what the retraction model is actually for. Retraction tracking
started with Mendeley version 7, so career-2017 through career-2022 carry no
retraction data at all: 955,512 rows where the column is NULL because nothing
was recorded, not because nothing was retracted. The model trained on
career-2023 and tested on career-2024 estimates what those six editions would
have said.

Predictions are joined back to real author identifiers through the key map,
because a prediction attached to entity 4471 is not something anyone can
read.

What this is not: an oracle. These are model estimates for a quantity that
was never measured, and they are labelled as estimates everywhere they
surface. The honest summary of their quality is the held-out score on
career-2024, which is reported alongside.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from rdl.train import CHECKPOINT_DIR, OUT_DIR, _to_device, pick_device

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "data_rdl" / "twopercenters"
KEYMAP_DIR = DATASET_DIR / "keymap"

# The column each task predicts, in the source data. Used only to find the
# NULL rows; the model never sees these.
SOURCE_COLUMN = {
    "retraction_exposure": "nc_rw",
    "retraction_exposed": "nc_rw",
    "own_retractions": "np_rw",
}


def unlabelled_rows(dataset, task_name: str) -> pd.DataFrame:
    """The fact rows whose target was never recorded.

    Read from the DATASET's view, not the task's: the task hides the column
    precisely so the model cannot see it, which also means the task's view
    cannot tell us which rows are missing it.
    """
    column = SOURCE_COLUMN[task_name]
    df = dataset.get_db(upto_test_timestamp=False).table_dict[
        "career_metrics"].df
    missing = df.loc[df[column].isna(), ["metric_id", "observation_date",
                                         "author_id", "edition_id"]]
    return missing.reset_index(drop=True)


def attach_ids(preds: pd.DataFrame, keymap: pd.DataFrame,
               on: str = "author_id") -> pd.DataFrame:
    """Turn integer graph indices back into the identifiers people use."""
    lookup = dict(zip(keymap["index"], keymap["original"]))
    out = preds.copy()
    out[on] = out[on].map(lookup)
    return out


def run(task_name: str, batch_size: int = 256, num_neighbors: int = 16,
        device: str | None = None, limit: int | None = None) -> Path:
    from relbench.base import TaskType
    from relbench.load import load_dataset
    from torch_geometric.loader import NeighborLoader

    from rdl import graph as rdl_graph
    from rdl.model import Model

    device = device or pick_device()
    checkpoint_path = CHECKPOINT_DIR / f"{task_name}.pt"
    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"no checkpoint at {checkpoint_path}. Train it first: "
            f"python -m rdl.train {task_name}")
    checkpoint = torch.load(checkpoint_path, weights_only=False)

    dataset = load_dataset(str(DATASET_DIR))
    task = dataset.load_task(task_name)
    data, col_stats = rdl_graph.build(task=task, dataset_dir=DATASET_DIR,
                                      upto_test_timestamp=False)

    targets = unlabelled_rows(dataset, task_name)
    if limit is not None:
        targets = targets.head(limit)
    logger.info("%d rows to score for %s", len(targets), task_name)

    model = Model(
        data=data,
        col_stats_dict=col_stats,
        out_channels=checkpoint["out_channels"],
        channels=checkpoint["channels"],
        num_layers=checkpoint["num_layers"],
    ).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    seeds = torch.tensor(targets["metric_id"].to_numpy(), dtype=torch.long)
    loader = NeighborLoader(
        data,
        num_neighbors=[num_neighbors] * checkpoint["num_layers"],
        time_attr="time",
        input_nodes=("career_metrics", seeds),
        # Each row is scored as of its own edition's timestamp, so the
        # temporal sampler shows it only what existed then. A 2018 row must
        # not be informed by 2024.
        input_time=data["career_metrics"].time[seeds],
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
    )

    chunks = []
    with torch.no_grad():
        for n, batch in enumerate(loader, start=1):
            batch = _to_device(batch, device)
            out = model(batch, "career_metrics").squeeze(-1)
            if task.task_type == TaskType.BINARY_CLASSIFICATION:
                out = torch.sigmoid(out)
            chunks.append(out.float().cpu())
            if n % 200 == 0:
                logger.info("scored %d batches", n)
    values = torch.cat(chunks).numpy()

    result = targets.copy()
    column = ("probability"
              if task.task_type == TaskType.BINARY_CLASSIFICATION
              else "value")
    result[column] = values
    result = attach_ids(result, pd.read_parquet(KEYMAP_DIR / "authors.parquet"))
    result = attach_ids(result,
                        pd.read_parquet(KEYMAP_DIR / "editions.parquet"),
                        on="edition_id")
    result["task"] = task_name
    result["is_estimate"] = True

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{task_name}_backfill.parquet"
    result.to_parquet(path, index=False)
    logger.info("wrote %d estimates to %s", len(result), path)

    metrics_path = OUT_DIR / f"{task_name}.json"
    held_out = None
    if metrics_path.exists():
        held_out = json.loads(metrics_path.read_text())["results"]["test"]
    logger.info("held-out quality of these estimates: %s", held_out)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--limit", type=int, default=None,
                        help="score only the first N rows (for a trial run)")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--num-neighbors", type=int, default=16)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.task, batch_size=args.batch_size,
        num_neighbors=args.num_neighbors, device=args.device,
        limit=args.limit)


if __name__ == "__main__":
    main()
