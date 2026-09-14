import pandas as pd
import pytest

from rdl.tasks import retraction


def test_all_three_retraction_columns_are_hidden_not_just_the_target():
    """nc_rw is the label, but np_rw and nc_to_rw are the same measurement
    from the same source arriving in the same edition. Leaving either in the
    graph leaks the answer."""
    removed = {tuple(pair) for pair in retraction.REMOVE_COLUMNS}
    assert ("career_metrics", "nc_rw") in removed
    assert ("career_metrics", "np_rw") in removed
    assert ("career_metrics", "nc_to_rw") in removed


def test_the_entity_is_the_fact_row_not_the_author():
    """The label lives on career_metrics, so that is the entity table and
    metric_id is the entity column."""
    assert retraction.MANIFEST["entity_table"] == "career_metrics"
    assert retraction.MANIFEST["entity_col"] == "metric_id"


def test_the_tasks_are_external_rather_than_autocomplete():
    """Autocomplete derives splits from the dataset's global timestamps and
    drops NULL targets. Every labelled row here sits after val_timestamp, so
    its train split would be empty. See the module docstring."""
    assert retraction.MANIFEST["kind"] == "external"


def test_nc_rw_is_the_regression_target_not_np_rw():
    """np_rw is 96.7% zero: a regression on it scores well by predicting
    zero for everyone."""
    assert retraction.TASKS["retraction_exposure"]["source_col"] == "nc_rw"
    assert retraction.TASKS["own_retractions"]["source_col"] == "np_rw"


def test_labelled_rows_are_only_the_two_tracked_editions():
    df = pd.read_parquet("data_parquet/career_metrics.parquet",
                         columns=["edition_id", "nc_rw"])
    labelled = set(df.loc[df["nc_rw"].notna(), "edition_id"].unique())
    assert labelled == {"career-2023", "career-2024"}


def test_the_unlabelled_count_is_what_we_measured():
    df = pd.read_parquet("data_parquet/career_metrics.parquet",
                         columns=["nc_rw"])
    assert int(df["nc_rw"].isna().sum()) == 955_512


def _toy():
    return pd.DataFrame({
        "observation_date": pd.to_datetime(
            ["2022-12-31"] * 4 + ["2023-12-31"] * 10 + ["2024-12-31"] * 6),
        "metric_id": range(20),
        "nc_rw": [None] * 4 + [0.0, 5.0] * 5 + [3.0] * 6,
        "np_rw": [None] * 4 + [0.0] * 10 + [1.0] * 6,
    })


def test_splits_cross_an_edition_boundary(tmp_path):
    """Train comes from 2023 and test from 2024. The real use imputes six
    editions the model has never seen a label for, so measuring across an
    edition boundary is the honest proxy; a random split inside the labelled
    editions would score better and mean less."""
    retraction.build_task("retraction_exposure", _toy(), tmp_path)
    train = pd.read_parquet(tmp_path / "retraction_exposure" / "train.parquet")
    test = pd.read_parquet(tmp_path / "retraction_exposure" / "test.parquet")
    assert set(train["observation_date"].dt.year) == {2023}
    assert set(test["observation_date"].dt.year) == {2024}


def test_unlabelled_editions_never_appear_in_any_split(tmp_path):
    retraction.build_task("retraction_exposure", _toy(), tmp_path)
    for split in ("train", "val", "test"):
        df = pd.read_parquet(tmp_path / "retraction_exposure" / f"{split}.parquet")
        assert 2022 not in set(df["observation_date"].dt.year)
        assert df["nc_rw"].notna().all()


def test_train_and_val_do_not_overlap(tmp_path):
    retraction.build_task("retraction_exposure", _toy(), tmp_path)
    d = tmp_path / "retraction_exposure"
    train = pd.read_parquet(d / "train.parquet")
    val = pd.read_parquet(d / "val.parquet")
    assert not set(train["metric_id"]) & set(val["metric_id"])


def test_binary_target_is_a_threshold_on_the_source_column(tmp_path):
    retraction.build_task("retraction_exposed", _toy(), tmp_path)
    train = pd.read_parquet(tmp_path / "retraction_exposed" / "train.parquet")
    assert "exposed" in train.columns
    assert set(train["exposed"].unique()) <= {0, 1}
    assert "nc_rw" not in train.columns


def test_building_refuses_when_an_edition_has_no_labels(tmp_path):
    """If the label distribution ever changes shape, fail loudly rather than
    write an empty split."""
    df = _toy()
    df.loc[df["observation_date"].dt.year == 2024, "nc_rw"] = None
    with pytest.raises(ValueError, match="expected labels"):
        retraction.build_task("retraction_exposure", df, tmp_path)
