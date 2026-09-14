import pandas as pd
import pytest

from rdl import build_dataset


def _toy():
    """Three authors and four fact rows, one of which points at a name that
    is not an author at all."""
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


SPECS = {
    "authors": build_dataset.Reindexable(pkey="author_id", time_col=None,
                                         fkeys={}),
    "career_metrics": build_dataset.Reindexable(
        pkey="metric_id", time_col="observation_date",
        fkeys={"author_id": "authors"}),
}


def test_primary_keys_become_zero_to_n_minus_one():
    out, _ = build_dataset.reindex(_toy(), SPECS)
    for name, df in out.items():
        pkey = SPECS[name].pkey
        assert list(df[pkey]) == list(range(len(df))), name


def test_fact_rows_are_time_sorted_before_indexing():
    """RelBench assigns indices in row order, so row order must mean
    something. Time order makes the key monotonic in time, which keeps the
    train/val/test boundaries contiguous ranges rather than scattered."""
    out, _ = build_dataset.reindex(_toy(), SPECS)
    assert out["career_metrics"]["observation_date"].is_monotonic_increasing


def test_ordering_is_deterministic_within_a_timestamp():
    """Two rows share 2019-12-31. Ties break on the original key so that two
    builds of the same input produce byte-identical output."""
    first, _ = build_dataset.reindex(_toy(), SPECS)
    second, _ = build_dataset.reindex(_toy(), SPECS)
    pd.testing.assert_frame_equal(first["career_metrics"],
                                  second["career_metrics"])


def test_foreign_keys_still_name_the_same_author_afterwards():
    """The real invariant: reindexing must not move anyone's rows onto a
    different person."""
    frames = _toy()
    before = dict(zip(frames["career_metrics"]["metric_id"],
                      frames["career_metrics"]["author_id"]))
    out, keymap = build_dataset.reindex(frames, SPECS)

    metric_original = dict(zip(keymap["career_metrics"]["index"],
                               keymap["career_metrics"]["original"]))
    author_original = dict(zip(keymap["authors"]["index"],
                               keymap["authors"]["original"]))

    for _, row in out["career_metrics"].iterrows():
        original_metric = metric_original[row["metric_id"]]
        expected_author = before[original_metric]
        if pd.isna(row["author_id"]):
            assert expected_author == "ghost"
        else:
            assert author_original[row["author_id"]] == expected_author


def test_dangling_foreign_keys_become_null_not_zero():
    """'ghost' is not an author. Mapping it to 0 would silently attribute
    those rows to whoever happens to sort first, which is the worst
    available failure: plausible and invisible."""
    out, _ = build_dataset.reindex(_toy(), SPECS)
    assert out["career_metrics"]["author_id"].isna().sum() == 1


def test_the_exact_expected_layout():
    """Pinned end to end, so a change in ordering rules cannot slip through
    as 'still passes'.

    authors sort by key:      a-1 -> 0, m-5 -> 1, z-9 -> 2
    metrics sort by (t, key): 100 -> 0, 500 -> 1, 700 -> 2, 900 -> 3
    """
    out, _ = build_dataset.reindex(_toy(), SPECS)
    assert list(out["authors"]["surname"]) == ["ada", "moe", "zed"]
    assert out["career_metrics"]["author_id"].tolist()[:2] == [2, 0]
    assert pd.isna(out["career_metrics"]["author_id"].iloc[2])
    assert out["career_metrics"]["author_id"].iloc[3] == 0


def test_keymap_round_trips():
    out, keymap = build_dataset.reindex(_toy(), SPECS)
    km = keymap["authors"].set_index("index")["original"]
    original_surnames = dict(zip(_toy()["authors"]["author_id"],
                                 _toy()["authors"]["surname"]))
    for i, original in km.items():
        assert out["authors"].loc[i, "surname"] == original_surnames[original]


def test_reindex_refuses_duplicate_primary_keys():
    """A duplicate key would make the mapping ambiguous and silently drop
    rows. Fail loudly instead."""
    frames = _toy()
    frames["authors"] = pd.concat(
        [frames["authors"], frames["authors"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        build_dataset.reindex(frames, SPECS)


# ---------------------------------------------------------------------------
# Integration checks against the real built dataset. These need
# data_rdl/twopercenters to exist, which `python -m rdl.build_dataset` makes.
# ---------------------------------------------------------------------------

DATASET = "data_rdl/twopercenters"


def _dataset():
    relbench_load = pytest.importorskip("relbench.load")
    import pathlib
    if not pathlib.Path(DATASET, "manifest.yaml").exists():
        pytest.skip("run `python -m rdl.build_dataset` first")
    return relbench_load.load_dataset(DATASET)


def test_relbench_accepts_the_built_dataset():
    """validate_and_correct_db raises unless every pkey is 0..n-1 in row
    order. This is the check the whole task exists to satisfy."""
    db = _dataset().get_db(upto_test_timestamp=False)
    assert len(db.table_dict["career_metrics"].df) == 1_402_942
    assert len(db.table_dict["authors"].df) == 818_667
    assert len(db.table_dict["editions"].df) == 8


def test_only_career_editions_are_in_the_graph():
    """The seven singleyr editions would be nodes no fact row references."""
    db = _dataset().get_db(upto_test_timestamp=False)
    assert set(db.table_dict["editions"].df["kind"]) == {"career"}


def test_test_timestamp_holds_out_exactly_the_2024_edition():
    ds = _dataset()
    upto = len(ds.get_db().table_dict["career_metrics"].df)
    full = len(ds.get_db(upto_test_timestamp=False)
               .table_dict["career_metrics"].df)
    assert full - upto == 230_333


def test_null_foreign_keys_match_the_career_half_of_the_source():
    """Plan 1 measured 22,327 rows with no institution and 33,370 with no
    country, but those were across career AND singleyr. This graph is career
    only, so the right figures are the career half: 10,967 and 16,657.
    Asserted explicitly because the larger numbers are the ones written down
    elsewhere, and a future reader will reach for them."""
    db = _dataset().get_db(upto_test_timestamp=False)
    cm = db.table_dict["career_metrics"].df
    assert int(cm["institution_id"].isna().sum()) == 10_967
    assert int(cm["country_code"].isna().sum()) == 16_657
    assert int(cm["author_id"].isna().sum()) == 0
    assert int(cm["edition_id"].isna().sum()) == 0


def test_the_imputation_target_is_untouched_by_reindexing():
    db = _dataset().get_db(upto_test_timestamp=False)
    cm = db.table_dict["career_metrics"].df
    assert int(cm["nc_rw"].isna().sum()) == 955_512


def test_fact_keys_are_monotonic_in_time():
    db = _dataset().get_db(upto_test_timestamp=False)
    cm = db.table_dict["career_metrics"].df
    assert cm["observation_date"].is_monotonic_increasing
    assert (cm["metric_id"].values == range(len(cm))).all()
