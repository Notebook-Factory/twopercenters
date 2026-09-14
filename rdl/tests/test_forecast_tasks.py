import pytest

from rdl.tasks import forecast


def test_no_query_uses_day_arithmetic():
    """A fixed-length window cannot track annual editions across leap years:
    2019-12-31 plus 365 days is 2020-12-30, one day short of the 2020
    edition, and with that window the dropout label came out exactly 100%
    for the 2019 and 2023 seeds while looking plausible for the other four.
    The seed timestamps drift too, running 2021-12-31, 2020-12-31,
    2020-01-01, 2019-01-01. Labels are defined in editions instead."""
    for cfg in forecast.ALL:
        assert "INTERVAL" not in cfg["sql"], cfg["name"]
        assert "{timedelta}" not in cfg["sql"], cfg["name"]


def test_every_forecast_task_has_sql_using_the_timestamps_relation():
    for cfg in forecast.ALL:
        assert cfg["sql"], cfg["name"]
        assert "timestamps" in cfg["sql"], cfg["name"]


def test_timedelta_fits_relbench_s_own_constraint():
    """RelBench refuses a timedelta larger than the gap between
    val_timestamp and test_timestamp, which is 365 days here."""
    import pandas as pd
    from rdl import spec
    gap = spec.TEST_TIMESTAMP - spec.VAL_TIMESTAMP
    assert pd.Timedelta(forecast.TIMEDELTA) <= gap


def test_the_population_is_the_most_recent_edition_not_all_history():
    """Counting every author who ever appeared makes someone who published
    once in 2017 a fresh dropout at every later timestamp, which measured
    43-46%. Anchoring to the most recent edition gives 14.5-18.6%, matching
    the 79-85% edition overlap."""
    for cfg in forecast.ALL:
        assert "MAX(observation_date)" in cfg["sql"], cfg["name"]


def test_the_label_comes_from_the_next_edition_strictly_after():
    """A window including the seed timestamp would make the label readable
    from the entity's own row."""
    for cfg in forecast.ALL:
        assert "MIN(observation_date)" in cfg["sql"], cfg["name"]
        assert "observation_date > t.timestamp" in cfg["sql"], cfg["name"]


def test_dropout_is_binary_over_the_next_edition():
    cfg = forecast.TASKS["dropout"]
    assert cfg["task_type"] == "binary_classification"
    assert cfg["target_col"] == "dropped_out"


def test_rank_and_score_are_regressions():
    assert forecast.TASKS["next_rank"]["task_type"] == "regression"
    assert forecast.TASKS["next_score"]["task_type"] == "regression"


def test_nothing_is_removed_because_the_label_is_a_future_row():
    """Unlike the retraction tasks, the label here is not a column of the
    entity row, so no column needs hiding. This year's rank predicting next
    year's rank is the baseline, not leakage."""
    assert forecast.REMOVE_COLUMNS == []


def test_manifests_declare_authors_as_the_entity(tmp_path):
    """These predict per author, unlike the retraction tasks which predict
    per fact row."""
    import yaml
    for name in forecast.TASKS:
        path = forecast.build_task(name, tmp_path)
        manifest = yaml.safe_load((path / "manifest.yaml").read_text())
        assert manifest["entity_table"] == "authors"
        assert manifest["entity_col"] == "author_id"
        assert manifest["kind"] == "forecast"
        assert manifest["timedelta"] == "365 days"
