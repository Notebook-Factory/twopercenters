"""Train one task and report it beside a baseline it has to beat.

The baseline is not decoration. Majority class already scores about 0.71
accuracy on the balanced retraction task and about 0.96 on the rare-event
one, and next year's cumulative citation count is nearly this year's, so a
number quoted on its own here would mislead anyone who reads it. Every result
this module produces carries the trivial baseline for the same split.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "data_rdl" / "twopercenters"
OUT_DIR = ROOT / "data_rdl" / "predictions"


def pick_device() -> str:
    """MPS on Apple Silicon, CUDA if present, otherwise CPU.

    CPU is a legitimate outcome, not a failure. Measured on the M4 Pro, a
    heterogeneous SAGE layer over 600k nodes and 800k edges runs at 69 ms on
    MPS against 81 ms on CPU: at this size the work is memory-bandwidth
    bound, so the accelerator buys about 1.2x rather than an order of
    magnitude.
    """
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def majority_baseline(y: np.ndarray) -> float:
    """Accuracy of always predicting the most common label."""
    y = np.asarray(y)
    if y.size == 0:
        raise ValueError("no labels to compute a baseline from")
    _, counts = np.unique(y, return_counts=True)
    return float(counts.max() / y.size)


def format_result(metrics: dict[str, float],
                  baseline: dict[str, float]) -> dict[str, Any]:
    """Pair a result with the baseline for the same split."""
    return {"metrics": dict(metrics), "baseline": dict(baseline)}


def _loss_for(task_type) -> torch.nn.Module:
    from relbench.base import TaskType

    if task_type == TaskType.BINARY_CLASSIFICATION:
        return torch.nn.BCEWithLogitsLoss()
    if task_type == TaskType.REGRESSION:
        return torch.nn.L1Loss()
    raise NotImplementedError(f"no loss wired for {task_type}")


def _out_channels(task_type) -> int:
    from relbench.base import TaskType

    if task_type in (TaskType.BINARY_CLASSIFICATION, TaskType.REGRESSION):
        return 1
    raise NotImplementedError(f"no head wired for {task_type}")


def run(
    task_name: str,
    epochs: int = 10,
    device: str | None = None,
    channels: int = 128,
    num_layers: int = 2,
    batch_size: int = 512,
    num_neighbors: int = 128,
    lr: float = 5e-3,
    dataset_dir: Path = DATASET_DIR,
) -> dict[str, Any]:
    from relbench.base import TaskType
    from relbench.load import load_dataset
    from relbench.modeling.graph import get_node_train_table_input
    from torch_geometric.loader import NeighborLoader

    from rdl import graph as rdl_graph
    from rdl.model import Model

    device = device or pick_device()
    logger.info("device: %s", device)

    dataset = load_dataset(str(dataset_dir))
    task = dataset.load_task(task_name)
    data, col_stats = rdl_graph.build(dataset_dir=dataset_dir)

    entity_table = task.entity_table
    loaders = {}
    for split in ("train", "val", "test"):
        table = task.get_table(split)
        table_input = get_node_train_table_input(table=table, task=task)
        loaders[split] = NeighborLoader(
            data,
            num_neighbors=[num_neighbors] * num_layers,
            time_attr="time",
            input_nodes=table_input.nodes,
            input_time=table_input.time,
            transform=table_input.transform,
            batch_size=batch_size,
            shuffle=(split == "train"),
            # MPS tensors do not survive being handed to worker processes.
            num_workers=0,
            persistent_workers=False,
        )

    model = Model(
        data=data,
        col_stats_dict=col_stats,
        out_channels=_out_channels(task.task_type),
        channels=channels,
        num_layers=num_layers,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = _loss_for(task.task_type)

    for epoch in range(1, epochs + 1):
        model.train()
        total, seen = 0.0, 0
        for batch in loaders["train"]:
            batch = batch.to(device)
            optimizer.zero_grad()
            pred = model(batch, entity_table).squeeze(-1)
            y = batch[entity_table].y.float()
            loss = loss_fn(pred, y)
            loss.backward()
            optimizer.step()
            total += float(loss) * y.numel()
            seen += y.numel()
        logger.info("epoch %d: train loss %.5f", epoch, total / max(seen, 1))

    results: dict[str, Any] = {}
    for split in ("val", "test"):
        pred = _predict(model, loaders[split], entity_table, device,
                        task.task_type)
        table = task.get_table(split, mask_input_cols=False)
        y_true = table.df[task.target_col].to_numpy()
        metrics = task.evaluate(pred, table)

        if task.task_type == TaskType.BINARY_CLASSIFICATION:
            baseline = {"majority_accuracy": majority_baseline(y_true),
                        "roc_auc": 0.5}
        else:
            baseline = task.evaluate(
                np.full_like(pred, float(np.median(y_true)), dtype=float),
                table)
            baseline = {f"median_{k}": v for k, v in baseline.items()}

        results[split] = format_result(metrics, baseline)
        logger.info("%s: %s", split, results[split])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": task_name,
        "task_type": str(task.task_type),
        "epochs": epochs,
        "device": device,
        "channels": channels,
        "num_layers": num_layers,
        "results": results,
    }
    (OUT_DIR / f"{task_name}.json").write_text(json.dumps(payload, indent=2))
    return payload


@torch.no_grad()
def _predict(model, loader, entity_table, device, task_type) -> np.ndarray:
    from relbench.base import TaskType

    model.eval()
    chunks = []
    for batch in loader:
        batch = batch.to(device)
        out = model(batch, entity_table).squeeze(-1)
        if task_type == TaskType.BINARY_CLASSIFICATION:
            out = torch.sigmoid(out)
        chunks.append(out.float().cpu())
    return torch.cat(chunks).numpy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--device", default=None)
    parser.add_argument("--channels", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=512)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(message)s")
    payload = run(args.task, epochs=args.epochs, device=args.device,
                  channels=args.channels, batch_size=args.batch_size)
    print(json.dumps(payload["results"], indent=2))


if __name__ == "__main__":
    main()
