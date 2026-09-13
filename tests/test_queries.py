"""Task 9: the four seam functions, now served from Postgres.

Every Elasticsearch access in the dashboard funnels through get_es_results,
es_result_pick, get_es_aggregate and base64_decode_and_decompress. These tests
pin the behaviour the eight layout modules depend on: the signatures, the shape
of the author data dict, and the fact that the three new editions (2022, 2023,
2024) are reachable.
"""
import math

import pytest

from citations_lib.utils import (
    base64_decode_and_decompress,
    edition_years,
    es_result_pick,
    get_es_aggregate,
    get_es_results,
    update_yr_options,
    yr_convention_map,
)


# ---------------------------------------------------------------- typeahead

def test_typeahead_returns_names_for_a_prefix():
    result = get_es_results("ioannidis", ["career", "singleyr"], "authfull")
    names = es_result_pick(result, "authfull")
    assert any("Ioannidis" in n for n in names)


def test_typeahead_is_still_typo_tolerant():
    result = get_es_results("ioanidis", ["career", "singleyr"], "authfull")
    assert es_result_pick(result, "authfull")


def test_typeahead_names_are_not_repeated():
    """One author can appear once per kind; the dropdown must not show the
    same name twice because of that."""
    result = get_es_results("ioannidis", ["career", "singleyr"], "authfull")
    names = es_result_pick(result, "authfull")
    assert len(names) == len(set(names))


def test_availability_probe_still_sees_both_kinds():
    """callback_templates.generate_update_carsing_callback reads
    result['_index'] and looks for the literal strings 'career' and
    'singleyr' in it."""
    result = get_es_results("Ioannidis, John P.A.", ["career", "singleyr"],
                            "authfull")
    kinds = list(result["_index"])
    assert "career" in kinds
    assert "singleyr" in kinds


# ------------------------------------------------------------- author data

def test_author_data_shape_matches_the_old_blob():
    result = get_es_results("Ioannidis, John P.A.", "career", "authfull")
    data = es_result_pick(result, "data", None)
    assert isinstance(data, dict)
    # Keys were "<prefix>_<year>" and "<prefix>_<year>_log"; layouts split on "_".
    assert any(k.startswith("career_") for k in data)
    assert any(k.endswith("_log") for k in data)


def test_new_editions_are_present():
    result = get_es_results("Ioannidis, John P.A.", "career", "authfull")
    data = es_result_pick(result, "data", None)
    for year in ("2022", "2023", "2024"):
        assert f"career_{year}" in data


def test_author_data_keys_use_underscores_not_hyphens():
    """edition_id in Postgres is 'career-2024', but get_auth_years and
    update_auth_yrs both recover the year with key.split('_')[-1]."""
    result = get_es_results("Ioannidis, John P.A.", "career", "authfull")
    data = es_result_pick(result, "data", None)
    assert not any("-" in k for k in data)
    for key in data:
        year = key.split("_")[-1]
        if year != "log":
            assert year.isdigit() and len(year) == 4


def test_author_data_carries_the_dashboard_metric_names():
    result = get_es_results("Ioannidis, John P.A.", "career", "authfull")
    data = es_result_pick(result, "data", None)
    row = data["career_2021"]
    for key in ("inst_name", "cntry", "sm-field", "self%", "nc", "h", "hm",
                "c", "rank", "nc (ns)", "h (ns)", "c (ns)"):
        assert key in row, key
    assert 0 <= row["self%"] <= 1


def test_log_values_are_computed_at_read_time_from_metric_maxima():
    result = get_es_results("Ioannidis, John P.A.", "career", "authfull")
    data = es_result_pick(result, "data", None)
    plain = data["career_2021"]
    logged = data["career_2021_log"]
    for metric in ("nc", "h", "hm", "ncs", "ncsf", "ncsfl", "c"):
        assert metric in logged
        assert 0.0 <= logged[metric] <= 1.0
    # The transform is log(x + 1) / log(max + 1); a value equal to the edition
    # maximum therefore lands exactly on 1.0, and everything else below it.
    assert logged["nc"] < 1.0
    assert logged["nc"] > math.log(plain["nc"] + 1) / math.log(1e12)


def test_singleyr_is_reported_separately_from_career():
    career = es_result_pick(
        get_es_results("Ioannidis, John P.A.", "career", "authfull"),
        "data", None)
    singleyr = es_result_pick(
        get_es_results("Ioannidis, John P.A.", "singleyr", "authfull"),
        "data", None)
    assert all(k.startswith("career_") for k in career)
    assert all(k.startswith("singleyr_") for k in singleyr)


def test_unknown_author_returns_the_nohit_value():
    result = get_es_results("zzzzzznosuchpersonzzzzzz", "career", "authfull")
    assert es_result_pick(result, "data", None) is None


# ---------------------------------------------------------- group aggregate

def test_group_aggregate_still_returns_summary_vectors():
    data = get_es_aggregate("cntry", "United States", "career")
    assert data


def test_country_aggregate_is_a_five_number_summary_plus_n():
    data = get_es_aggregate("cntry", "United States", "career")
    vector = data["career_2021"]["nc"]
    assert len(vector) == 6
    assert vector[0] <= vector[1] <= vector[2] <= vector[3] <= vector[4]
    assert vector[5] > 0


def test_field_aggregate_has_the_same_shape_as_country():
    country = get_es_aggregate("cntry", "United States", "career")
    field = get_es_aggregate("sm-field", "Clinical Medicine", "career")
    assert set(field["career_2021"]) == set(country["career_2021"])
    assert len(field["career_2021"]["h"]) == 6


def test_institution_aggregate_has_the_same_shape_as_country():
    """Institution aggregates are computed live rather than materialised
    (R21); callers must not be able to tell."""
    country = get_es_aggregate("cntry", "United States", "career")
    inst = get_es_aggregate("inst_name", "Stanford University", "career")
    assert inst
    assert set(inst["career_2021"]) == set(country["career_2021"])
    assert len(inst["career_2021"]["h"]) == 6


def test_group_aggregates_reach_the_new_editions():
    for group, name in (("cntry", "United States"),
                        ("sm-field", "Clinical Medicine"),
                        ("inst_name", "Stanford University")):
        data = get_es_aggregate(group, name, "career")
        for year in ("2022", "2023", "2024"):
            assert f"career_{year}" in data, (group, year)


def test_group_aggregate_has_log_variants():
    """group_vs_group_layout reads data[f'{prefix}_{yr}_log'] too."""
    data = get_es_aggregate("cntry", "United States", "career")
    logged = data["career_2021_log"]["nc"]
    assert len(logged) == 6
    assert all(0.0 <= v <= 1.0 for v in logged[:5])
    assert logged[5] == data["career_2021"]["nc"][5]


def test_unknown_group_returns_empty_rather_than_raising():
    assert get_es_aggregate("inst_name", "No Such University", "career") == {}


# ------------------------------------------------------- edition year maps

def test_edition_years_come_from_postgres():
    assert edition_years("career") == [2017, 2018, 2019, 2020, 2021, 2022,
                                       2023, 2024]
    assert edition_years("singleyr") == [2017, 2019, 2020, 2021, 2022, 2023,
                                         2024]


def test_yr_convention_map_covers_every_radio_index():
    """The six hardcoded copies of this map in group_vs_group_layout and
    author_vs_group_layout stopped at index 4, so the three new editions
    raised KeyError."""
    career = yr_convention_map(True)
    assert career["0"] == "2017"
    assert career["7"] == "2024"
    options = update_yr_options(career=True)
    for option in options:
        assert str(option["value"]) in career


def test_yr_convention_map_matches_the_singleyr_radio():
    singleyr = yr_convention_map(False)
    options = update_yr_options(career=False)
    for option in options:
        if option.get("disabled"):
            continue
        assert str(option["value"]) in singleyr
    assert singleyr[str(len(singleyr) - 1)] == "2024"


# -------------------------------------------------------------- dead shim

def test_base64_shim_fails_loudly():
    with pytest.raises(RuntimeError) as excinfo:
        base64_decode_and_decompress("anything")
    assert "es_result_pick" in str(excinfo.value)


# -------------------------------------------------------------- world map

def test_world_map_covers_the_new_editions():
    """get_world_df used to read aggregate/cntry_career.pkl, which stops at
    2021, and its except branch turned a missing year into a map of zeros
    rather than an error."""
    from citations_lib.utils import get_world_df

    old = get_world_df("2021", "median", "career")
    new = get_world_df("2024", "median", "career")
    assert list(new.columns) == list(old.columns)
    assert not new.empty
    assert (new["metric_name"] == "lel").sum() == 0
    assert new["median"].sum() > 0
    assert set(new["metric"]) == {"h", "nc", "hm", "ncs", "ncsf", "ncsfl", "c"}
    assert new.loc[new["code"] == "USA", "median"].notna().all()


# --------------------------------------------------- group dropdown options

def test_dropdown_opts_covers_every_edition_in_postgres():
    """The two group pages used to build this from aggregate/info_*.pkl,
    nine files covering radio indices career 0-4 and singleyr 0-3. Selecting
    2022 asked for 'career 5' and raised KeyError."""
    from citations_lib.utils import edition_years, load_dropdown_opts

    opts = load_dropdown_opts()
    for kind in ("career", "singleyr"):
        years = edition_years(kind)
        for index in range(len(years)):
            assert f"{kind} {index}" in opts, f"{kind} {index}"
    # The three editions this project adds, at the indices the year radio
    # hands the callback.
    career = edition_years("career")
    for year in (2022, 2023, 2024):
        assert f"career {career.index(year)}" in opts
    singleyr = edition_years("singleyr")
    for year in (2022, 2023, 2024):
        assert f"singleyr {singleyr.index(year)}" in opts


def test_dropdown_opts_entries_have_the_pickles_shape():
    from citations_lib.utils import load_dropdown_opts

    entry = load_dropdown_opts()["career 7"]
    for metric in ("nc", "h", "hm", "ncs", "ncsf", "ncsfl",
                   "nc (ns)", "h (ns)", "hm (ns)", "ncs (ns)",
                   "ncsf (ns)", "ncsfl (ns)"):
        for stat in ("min", "max", "mean", "std"):
            assert f"{metric} {stat}" in entry, f"{metric} {stat}"
    for listkey in ("cntry", "cntry_full", "inst_name", "sm-field"):
        assert entry[listkey], listkey
    # The group dropdown zips these two together to label the countries.
    assert len(entry["cntry"]) == len(entry["cntry_full"])


def test_dropdown_opts_drops_country_codes_with_no_name():
    """csk, scg and sux are defunct states country_converter cannot resolve.
    They would show as 'not found' in the dropdown and then fail the same
    conversion inside get_es_aggregate."""
    from citations_lib.utils import load_dropdown_opts

    for entry in load_dropdown_opts().values():
        assert not ({"csk", "scg", "sux"} & set(entry["cntry"]))
        assert "not found" not in entry["cntry_full"]


def test_dropdown_opts_matches_the_pickles_where_they_exist():
    """The nine pickles are a cross-check, not the truth: the notebook that
    wrote them floored the fractional hm-index for min and max. Everything
    else agrees exactly."""
    import math
    import pickle

    from citations_lib.utils import load_dropdown_opts

    computed = load_dropdown_opts()
    for kind, count in (("career", 5), ("singleyr", 4)):
        for i in range(count):
            with open(f"aggregate/info_{kind}_{i}.pkl", "rb") as fp:
                old = pickle.load(fp)
            new = computed[f"{kind} {i}"]
            for key, value in old.items():
                if isinstance(value, list):
                    continue
                if key.startswith("hm") and key.rsplit(" ", 1)[1] in ("min", "max"):
                    assert math.floor(new[key]) == value, (kind, i, key)
                else:
                    assert float(new[key]) == float(value), (kind, i, key)


def test_dropdown_opts_reads_the_materialized_views_not_the_fact_tables():
    """Review FINDING 4.

    load_dropdown_opts builds both group pages, so it runs inside a callback,
    once per worker process. It used to answer four `group by` scans over
    both fact tables (2,730,673 rows) and measured about 3 seconds warm here,
    7.2 on the reviewer's machine. Migration 007 precomputes both halves, the
    same trade group_metrics already makes.

    This asserts the reader actually goes to the views. A regression to
    scanning the fact tables would still return the right answer, just
    slowly, and slowly is the thing being fixed.
    """
    import citations_lib.utils as utils

    seen = []
    real = utils._fetch
    utils._fetch = lambda sql, params=(): (seen.append(sql), real(sql, params))[1]
    try:
        utils.load_dropdown_opts.cache_clear()
        utils.load_dropdown_opts()
    finally:
        utils._fetch = real
        utils.load_dropdown_opts.cache_clear()

    joined = " ".join(seen)
    assert "dropdown_options" in joined
    assert "dropdown_stats" in joined
    for table in ("career_metrics", "singleyr_metrics"):
        assert table not in joined, (
            f"load_dropdown_opts scanned {table} again: "
            "that is the 3-to-7 second callback FINDING 4 removed"
        )


def test_dropdown_opts_is_fast_enough_to_sit_in_a_callback():
    """A loose ceiling, not a benchmark.

    The point is to fail if someone puts a fact-table scan back on this path,
    not to police tenths of a second, so the bound is set well above the
    measured 0.57s and well below the 3s this replaced.
    """
    import time

    from citations_lib.utils import load_dropdown_opts

    load_dropdown_opts()  # let the connection and the OS page cache settle
    load_dropdown_opts.cache_clear()
    started = time.time()
    load_dropdown_opts()
    elapsed = time.time() - started
    load_dropdown_opts.cache_clear()
    assert elapsed < 2.0, f"load_dropdown_opts took {elapsed:.2f}s"


# --------------------------------------------------------- world map labels

def test_world_map_never_labels_a_country_as_a_different_country():
    """Review FINDING 5.

    get_world_df used to hand three unresolvable codes a hardcoded name, and
    two of those names belonged to somewhere else: scg (Serbia and
    Montenegro) was drawn as the Czech Republic and ant (the Netherlands
    Antilles) as the Netherlands. All four unresolvable codes are excluded
    now, which is what the group dropdowns already did with them.
    """
    from citations_lib.utils import edition_years, get_world_df

    year = edition_years("career")[-1]
    df = get_world_df(year, "median", "career")
    codes = set(df["code"])
    assert not ({"CSK", "SCG", "SUX", "ANT"} & codes), codes
    assert "Czech Republic" not in set(
        df[df["code"] == "SCG"]["country"]), "scg is still labelled"
    # The real countries are all still there.
    assert {"USA", "DEU", "TUR"} <= codes
    assert not df.empty


def test_world_map_names_match_the_dropdown_names():
    """One rule for what a country code is called, not two."""
    from citations_lib.utils import _country_full_name, edition_years, get_world_df

    year = edition_years("career")[-1]
    df = get_world_df(year, "median", "career")
    for code, name in zip(df["code"], df["country"]):
        assert name == _country_full_name(code.lower()), code
