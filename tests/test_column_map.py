import pytest
from pipeline.column_map import canonical


@pytest.mark.parametrize("raw,expected", [
    # the year-stamped metric names, across editions
    ("np6017", "np"), ("np6024", "np"),
    ("nc9617", "nc"), ("nc9624", "nc"),
    ("h17", "h"), ("h24", "h"),
    ("hm17", "hm"), ("hm24", "hm"),
    ("np6019 cited9619", "np_cited"),
    ("np6024 cited9624", "np_cited"),
    # self-citations-excluded variants
    ("nc9624 (ns)", "nc_ns"),
    ("rank (ns)", "rank_ns"),
    ("np6024 cited9624 (ns)", "np_cited_ns"),
    # the version 7 retraction columns
    ("np6024_rw", "np_rw"),
    ("nc9624_to_rw", "nc_to_rw"),
    ("nc9624_rw", "nc_rw"),
    # the version 3-6 columns they replaced
    ("np6022_d", "np_d"),
    ("nc9622_d", "nc_d"),
    # stable names
    ("authfull", "authfull"), ("inst_name", "inst_name"), ("cntry", "cntry"),
    ("firstyr", "firstyr"), ("lastyr", "lastyr"), ("c", "c"), ("rank", "rank"),
    ("self%", "self_pct"),
    ("rank sm-subfield-1", "rank_subfield"),
    ("rank sm-subfield-1 (ns)", "rank_subfield_ns"),
    ("sm-subfield-1 count", "subfield_count"),
    # the 2017 rename
    ("npsf", "cpsf"), ("npsf (ns)", "cpsf_ns"),
    # the 2017 taxonomy, mapped onto the later scheme
    ("name1", "sm-subfield-1"), ("frac1", "sm-subfield-1-frac"),
    ("name22", "sm-field"), ("frac22", "sm-field-frac"),
])
def test_canonical_names(raw, expected):
    assert canonical(raw) == expected


def test_unmapped_columns_are_dropped_not_guessed():
    # 2017's numeric taxonomy codes have no equivalent in later editions
    assert canonical("sm-1") is None
    assert canonical("sm22") is None


def test_nc_to_rw_is_not_confused_with_nc_rw():
    assert canonical("nc9624_to_rw") != canonical("nc9624_rw")
