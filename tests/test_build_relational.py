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
