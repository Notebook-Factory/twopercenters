import numpy as np
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


def test_majority_baseline_on_an_imbalanced_label():
    """The rare-event retraction task is about 96% zero. A model reporting
    0.96 accuracy there has learned nothing, which is why the baseline has
    to sit beside every number."""
    y = np.array([0] * 96 + [1] * 4)
    assert train.majority_baseline(y) == pytest.approx(0.96)


def test_majority_baseline_on_a_balanced_label():
    assert train.majority_baseline(np.array([1, 1, 1, 0])) == pytest.approx(0.75)


def test_majority_baseline_refuses_an_empty_split():
    with pytest.raises(ValueError, match="no labels"):
        train.majority_baseline(np.array([]))


def test_every_result_carries_a_baseline():
    """A score with no baseline beside it is not a result."""
    out = train.format_result({"roc_auc": 0.81}, {"roc_auc": 0.50})
    assert out["metrics"]["roc_auc"] == 0.81
    assert out["baseline"]["roc_auc"] == 0.50


def test_format_result_copies_rather_than_aliases():
    """Guards against a later epoch mutating an already-recorded result."""
    metrics = {"roc_auc": 0.81}
    out = train.format_result(metrics, {})
    metrics["roc_auc"] = 0.99
    assert out["metrics"]["roc_auc"] == 0.81


def test_binary_and_regression_have_a_loss_and_a_head():
    from relbench.base import TaskType
    for task_type in (TaskType.BINARY_CLASSIFICATION, TaskType.REGRESSION):
        assert train._loss_for(task_type) is not None
        assert train._out_channels(task_type) == 1


def test_an_unwired_task_type_raises_rather_than_guessing():
    from relbench.base import TaskType
    with pytest.raises(NotImplementedError):
        train._loss_for(TaskType.RECOMMENDATION)


def test_regression_forecast_tasks_declare_a_persistence_column():
    """The median baseline flatters a model on a persistent quantity: it
    scored 0.93 on next_rank where the model got 0.295 and simply repeating
    this year's rank got 0.079. Any regression forecast task must name the
    column it should be compared against, so that cannot happen silently."""
    from rdl.tasks import forecast
    for name, cfg in forecast.TASKS.items():
        if cfg["task_type"] == "regression":
            assert cfg.get("persistence_col"), name


def test_persistence_column_lookup_handles_unknown_tasks():
    assert train._persistence_column("retraction_exposed") is None
    assert train._persistence_column("next_rank") == "rank"
