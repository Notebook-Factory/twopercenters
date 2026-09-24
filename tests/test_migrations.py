import os
import psycopg
import pytest
from db.migrate import apply_all

from conftest import assert_distinct_urls

DSN = os.environ["DATABASE_URL"]
TEST_DSN = os.environ["TEST_DATABASE_URL"]


@pytest.fixture
def conn():
    assert_distinct_urls(TEST_DSN, DSN)
    with psycopg.connect(TEST_DSN) as c:
        c.execute("drop schema public cascade; create schema public;")
        c.commit()
        yield c


def test_conn_fixture_refuses_to_drop_the_development_database():
    # R23: the fixture drops and recreates the public schema, so it must
    # refuse outright if TEST_DATABASE_URL and DATABASE_URL ever collapse to
    # the same database.
    with pytest.raises(AssertionError, match="TEST_DATABASE_URL must not equal DATABASE_URL"):
        assert_distinct_urls(DSN, DSN)


def test_apply_all_creates_tables_and_is_idempotent(conn):
    first = apply_all(conn, "db/migrations")
    assert "001_schema.sql" in first

    tables = {
        r[0] for r in conn.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'public'"
        ).fetchall()
    }
    for expected in ["authors", "editions", "career_metrics", "singleyr_metrics",
                     "institutions", "countries", "fields", "subfields",
                     "author_name_observations", "metric_maxima"]:
        assert expected in tables

    second = apply_all(conn, "db/migrations")
    assert second == []


def test_career_metrics_rejects_orphan_author(conn):
    apply_all(conn, "db/migrations")
    conn.execute("insert into editions (edition_id, mendeley_version, data_year, "
                 "kind, observation_date) values ('career_2024', 8, 2024, "
                 "'career', '2024-12-31')")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("insert into career_metrics (author_id, edition_id, "
                     "observation_date) values ('nosuchauthor', 'career_2024', "
                     "'2024-12-31')")
