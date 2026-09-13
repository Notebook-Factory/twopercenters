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
