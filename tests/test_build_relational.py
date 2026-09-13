import json
import os

import psycopg
import pytest

from db.migrate import apply_all
from pipeline.build_relational import (build, load_edition,
                                       refresh_dropdown_views,
                                       refresh_group_metrics)

from conftest import assert_distinct_urls

DSN = os.environ["DATABASE_URL"]
TEST_DSN = os.environ["TEST_DATABASE_URL"]


@pytest.fixture
def conn():
    assert_distinct_urls(TEST_DSN, DSN)
    with psycopg.connect(TEST_DSN) as c:
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


def test_refresh_group_metrics_populates_the_view(conn):
    # R24: group_metrics is a materialized view, so it stays at whatever it
    # held when it was last refreshed -- ispopulated does not mean non-empty.
    load_edition(conn, "data_clean/version-8", kind="career")
    refresh_group_metrics(conn)
    rows = conn.execute("select count(*) from group_metrics").fetchone()[0]
    assert rows > 0


def test_refresh_group_metrics_is_a_no_op_if_the_view_does_not_exist_yet(conn):
    conn.execute("drop materialized view group_metrics")
    conn.commit()
    refresh_group_metrics(conn)  # must not raise


@pytest.fixture
def one_edition_root(tmp_path):
    """A data_clean/ containing exactly one version directory.

    build() now refuses to run with no editions (review FINDING 3), so the
    tests below that only care about what build() calls at the end need a
    root it will accept. The directory is a symlink to the real
    data_clean/version-8 and the loader is stubbed out, so nothing is
    actually read from it.
    """
    root = tmp_path / "data_clean"
    root.mkdir()
    (root / "version-8").symlink_to(
        os.path.abspath("data_clean/version-8"), target_is_directory=True)
    return root


def test_build_refuses_to_run_with_no_editions(conn, tmp_path):
    """R24, on the first command anyone runs on a fresh host.

    data_clean/ is gitignored, so a fresh `git push dokku` carries no data at
    all. Before this, build() globbed an empty directory, loaded nothing,
    wrote empty Parquet, refreshed group_metrics down to zero rows, printed
    "total 0 rows" and exited 0 -- a silent empty build on the code path
    where it is most likely to happen.
    """
    empty_root = tmp_path / "data_clean"
    empty_root.mkdir()
    with pytest.raises(SystemExit) as caught:
        build(conn, root=str(empty_root), out_dir=str(tmp_path / "out"))
    assert "no editions found" in str(caught.value)


def test_build_refuses_to_run_when_the_root_does_not_exist_at_all(conn, tmp_path):
    with pytest.raises(SystemExit):
        build(conn, root=str(tmp_path / "absent"),
              out_dir=str(tmp_path / "out"))


def test_nothing_is_refreshed_when_the_build_refuses(conn, tmp_path, monkeypatch):
    """The refusal has to come before the refreshes, or an empty build still
    empties the views on its way out."""
    calls = []
    monkeypatch.setattr("pipeline.build_relational.refresh_group_metrics",
                        lambda c: calls.append("group_metrics"))
    monkeypatch.setattr("pipeline.build_relational.refresh_dropdown_views",
                        lambda c: calls.append("dropdown_views"))
    empty_root = tmp_path / "data_clean"
    empty_root.mkdir()
    with pytest.raises(SystemExit):
        build(conn, root=str(empty_root), out_dir=str(tmp_path / "out"))
    assert calls == []


def test_build_refreshes_group_metrics_as_its_final_step(
        conn, tmp_path, monkeypatch, one_edition_root):
    calls = []
    monkeypatch.setattr("pipeline.build_relational._load_file",
                        lambda c, e: 0)
    monkeypatch.setattr(
        "pipeline.build_relational.refresh_group_metrics",
        lambda c: calls.append(c),
    )
    build(conn, root=str(one_edition_root),
          out_dir=str(tmp_path / "data_parquet"))
    assert calls == [conn]


def test_build_refreshes_the_dropdown_views_too(
        conn, tmp_path, monkeypatch, one_edition_root):
    """dropdown_options and dropdown_stats (migration 007) are materialized
    views like group_metrics, so they are just as stale after a load unless
    the build refreshes them."""
    calls = []
    monkeypatch.setattr("pipeline.build_relational._load_file",
                        lambda c, e: 0)
    monkeypatch.setattr(
        "pipeline.build_relational.refresh_dropdown_views",
        lambda c: calls.append(c),
    )
    build(conn, root=str(one_edition_root),
          out_dir=str(tmp_path / "data_parquet"))
    assert calls == [conn]


def test_refresh_dropdown_views_populates_both_views(conn):
    load_edition(conn, "data_clean/version-8", kind="career")
    refresh_dropdown_views(conn)
    for view in ("dropdown_options", "dropdown_stats"):
        rows = conn.execute(f"select count(*) from {view}").fetchone()[0]
        assert rows > 0, view


def test_refresh_dropdown_views_is_a_no_op_if_they_do_not_exist_yet(conn):
    conn.execute("drop materialized view dropdown_options")
    conn.execute("drop materialized view dropdown_stats")
    conn.commit()
    refresh_dropdown_views(conn)  # must not raise
