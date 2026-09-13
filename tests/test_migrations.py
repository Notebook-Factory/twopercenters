import os
import psycopg
import pytest
from db.migrate import apply_all

DSN = os.environ["DATABASE_URL"]


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as c:
        c.execute("drop schema public cascade; create schema public;")
        c.commit()
        yield c


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
