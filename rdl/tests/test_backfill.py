import pandas as pd
import pytest

from rdl import backfill


def test_attach_ids_turns_graph_indices_back_into_identifiers():
    """A prediction attached to entity 4471 is not something anyone can
    read. The key map is what makes the output usable."""
    preds = pd.DataFrame({"author_id": [0, 2], "value": [3.5, 0.0]})
    keymap = pd.DataFrame({"index": [0, 1, 2],
                           "original": ["a-1", "m-5", "z-9"]})
    out = backfill.attach_ids(preds, keymap)
    assert list(out["author_id"]) == ["a-1", "z-9"]
    assert list(out["value"]) == [3.5, 0.0]


def test_attach_ids_does_not_mutate_its_input():
    preds = pd.DataFrame({"author_id": [0], "value": [1.0]})
    keymap = pd.DataFrame({"index": [0], "original": ["a-1"]})
    backfill.attach_ids(preds, keymap)
    assert preds["author_id"].iloc[0] == 0


def test_every_task_declares_the_column_it_imputes():
    from rdl.tasks import retraction
    assert set(backfill.SOURCE_COLUMN) == set(retraction.TASKS)


def test_missing_checkpoint_says_how_to_make_one():
    """Scoring before training is an easy mistake to make. The error should
    name the command that fixes it rather than just failing to open a file."""
    with pytest.raises(FileNotFoundError, match="python -m rdl.train"):
        backfill.run("no_such_task", device="cpu", limit=1)


def test_output_is_labelled_as_an_estimate():
    """These are model estimates for a quantity that was never measured.
    Anything that surfaces them has to be able to say so."""
    import inspect
    source = inspect.getsource(backfill.run)
    assert 'result["is_estimate"] = True' in source
