import json
import os

import psycopg
import pytest

from db.migrate import apply_all
from pipeline.build_relational import load_edition

DSN = os.environ["DATABASE_URL"]


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as c:
        c.execute("drop schema public cascade; create schema public;")
        c.commit()
        apply_all(c, "db/migrations")
        yield c


def test_loading_one_edition_preserves_every_row(conn):
    rows = load_edition(conn, "data_clean/version-8", kind="career")
    loaded = conn.execute("select count(*) from career_metrics").fetchone()[0]
    assert loaded == rows == 230333


def test_no_author_row_is_dropped_on_name_collision(conn):
    load_edition(conn, "data_clean/version-5", kind="career")
    loaded = conn.execute("select count(*) from career_metrics").fetchone()[0]
    # The old create_composite_dict kept selected_data[0] and lost ~3,232 rows.
    assert loaded == 194983


def test_year_stamped_columns_are_gone(conn):
    load_edition(conn, "data_clean/version-8", kind="career")
    columns = {r[0] for r in conn.execute(
        "select column_name from information_schema.columns "
        "where table_name = 'career_metrics'").fetchall()}
    assert "np" in columns and "nc" in columns and "h" in columns
    assert not any(c.startswith("np60") or c.startswith("nc96") for c in columns)


def test_version_1_carries_both_career_years_and_records_the_subfield_gap(conn):
    # version-1 is the only directory holding two career data years.
    rows = load_edition(conn, "data_clean/version-1", kind="career")
    assert rows == 105026 + 105000

    per_year = dict(conn.execute(
        "select data_year, count(*) from career_metrics m "
        "join editions e using (edition_id) group by 1 order by 1").fetchall())
    assert per_year == {2017: 105026, 2018: 105000}

    present = conn.execute(
        "select columns_present from editions where edition_id = 'career-2017'"
    ).fetchone()[0]
    present = present if isinstance(present, list) else json.loads(present)
    # RULING R7: column_map drops 2017's name2/frac2, so there is no second
    # subfield in this edition. The gap is recorded rather than left silent.
    assert "sm-subfield-1" in present
    assert "sm-subfield-2" not in present
    assert conn.execute(
        "select count(*) from career_metrics where subfield_2_id is not null"
    ).fetchone()[0] == 0


def test_dimension_values_are_nfkc_normalised_before_deduplication(conn):
    # RULING R15: 'CEA LETI\xa0' must not become a second institution.
    load_edition(conn, "data_clean/version-5", kind="career")
    names = [r[0] for r in conn.execute(
        "select inst_name from institutions where inst_name like 'CEA LETI%'"
    ).fetchall()]
    assert names == ["CEA LETI"]

    assert conn.execute(
        "select count(*) from institutions where inst_name <> btrim(inst_name)"
    ).fetchone()[0] == 0
    assert conn.execute(
        "select count(*) from institutions where inst_name like '%' || chr(160) || '%'"
    ).fetchone()[0] == 0


def test_every_edition_metric_gets_a_maximum(conn):
    load_edition(conn, "data_clean/version-8", kind="career")
    maxima = dict(conn.execute(
        "select metric, max_value from metric_maxima "
        "where edition_id = 'career-2024'").fetchall())
    assert maxima["np"] == conn.execute(
        "select max(np) from career_metrics").fetchone()[0]
    assert maxima["nc"] == conn.execute(
        "select max(nc) from career_metrics").fetchone()[0]
    assert "h" in maxima and "hm" in maxima


def test_a_row_without_an_institution_still_carries_its_own_country(conn):
    # RULING R17. 695 rows across the editions have no inst_name but do have a
    # cntry: 155 in career 2018 and 540 in singleyr 2019. Reading country back
    # through institutions loses every one of them.
    load_edition(conn, "data_clean/version-1", kind="career")
    row = conn.execute("""
        select m.country_code, m.institution_id
        from career_metrics m
        join author_name_observations o
          on o.author_id = m.author_id and o.edition_id = m.edition_id
        where m.edition_id = 'career-2018'
          and o.authfull_raw = 'Harley, Calvin B.'
    """).fetchone()
    assert row is not None
    assert row[1] is None, "this row has no institution in the source"
    assert row[0] == "usa"


def test_a_row_keeps_its_own_country_not_its_institutions(conn):
    # RULING R17. 'Department of Psychiatry' is first seen in career 2024 with
    # 'usa', but Bullmore's row carries 'gbr'. 1,170 rows of that edition
    # disagree with their institution's first-seen country.
    load_edition(conn, "data_clean/version-8", kind="career")
    row = conn.execute("""
        select m.country_code, i.country_code, i.inst_name
        from career_metrics m
        join institutions i on i.institution_id = m.institution_id
        join author_name_observations o
          on o.author_id = m.author_id and o.edition_id = m.edition_id
        where m.edition_id = 'career-2024'
          and o.authfull_raw = 'Bullmore, Edward T.'
    """).fetchone()
    assert row is not None
    assert row[2] == "Department of Psychiatry"
    assert row[1] == "usa", "the institution's own country is unchanged"
    assert row[0] == "gbr", "the row must carry its own country"


def test_null_country_matches_the_rows_whose_source_country_is_empty(conn):
    # The only rows left without a country are the ones the source leaves
    # empty: 252 of career 2024's 230,333, and 128 of career 2018's 105,000.
    # Not the 22,327 rows that merely have no institution.
    # Ascending data-year order, oldest first. Identity resolution is
    # incremental (RULING R4), so loading 2024 before 2017 would produce
    # author ids a real build never produces. _check_load_order now refuses it.
    load_edition(conn, "data_clean/version-1", kind="career")
    load_edition(conn, "data_clean/version-8", kind="career")
    empty = dict(conn.execute(
        "select edition_id, count(*) from career_metrics "
        "where country_code is null group by 1").fetchall())
    assert empty == {"career-2024": 252, "career-2018": 128, "career-2017": 10067}


def test_loading_an_older_edition_after_a_newer_one_is_refused(conn):
    # RULING R4 makes identity resolution incremental, so descending order
    # silently produces author ids a real build never produces. The invariant
    # is enforced rather than only documented.
    load_edition(conn, "data_clean/version-8", kind="career")
    with pytest.raises(ValueError, match="ascending data-year order"):
        load_edition(conn, "data_clean/version-5", kind="career")
    # The refusal happens before anything is written.
    assert conn.execute(
        "select count(*) from career_metrics").fetchone()[0] == 230333


def test_career_2018_may_follow_singleyr_2017_because_the_check_is_per_kind(conn):
    # A real build interleaves kinds: version 1 carries two career years but
    # only one singleyr year, so career 2018 is loaded before singleyr 2017.
    # A global order check would reject that; a per-kind one must not.
    load_edition(conn, "data_clean/version-1", kind="career")   # 2017 then 2018
    load_edition(conn, "data_clean/version-1", kind="singleyr")  # 2017
    kinds = dict(conn.execute(
        "select kind, max(data_year) from editions group by 1").fetchall())
    assert kinds == {"career": 2018, "singleyr": 2017}
