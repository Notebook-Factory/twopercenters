"""Shared pytest setup.

pytest does not load .env on its own, and the test modules read
os.environ["DATABASE_URL"] / os.environ["ELASTICSEARCH_URL"] directly. This
file loads .env first (if present) so a real value there wins, and then fills
in the same local defaults as .env.example for anything still unset, so the
test suite works out of the box against the docker-compose services.

TEST_DATABASE_URL is the destination for the fixtures that drop and recreate
the public schema (tests/test_build_relational.py, tests/test_migrations.py).
It defaults to the same host and credentials as DATABASE_URL's default, but a
different database name, so running the suite never touches the development
database (see R23). A real TEST_DATABASE_URL environment variable still wins,
the same way it already does for DATABASE_URL.
"""
import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

_DEFAULTS = {
    "DATABASE_URL": "postgresql://twopct:twopct@localhost:5433/twopct",
    "TEST_DATABASE_URL": "postgresql://twopct:twopct@localhost:5433/twopct_test",
    "ELASTICSEARCH_URL": "http://localhost:9201",
}

for _key, _value in _DEFAULTS.items():
    os.environ.setdefault(_key, _value)


def assert_distinct_urls(test_url, dev_url):
    """Refuse to proceed if the schema-dropping fixtures would point at the
    development database (R23). Kept as a standalone function so the guard
    itself is exercised by a test rather than only trusted by inspection."""
    assert test_url != dev_url, (
        "TEST_DATABASE_URL must not equal DATABASE_URL: refusing to run a "
        "schema-dropping fixture against the development database"
    )


def _ensure_database_exists(url):
    """Create the database TEST_DATABASE_URL names, if it does not exist yet.

    CREATE DATABASE cannot run inside a transaction, so this connects to the
    'postgres' maintenance database with autocommit rather than the target
    database itself.
    """
    parts = urlsplit(url)
    dbname = parts.path.lstrip("/")
    maintenance_url = urlunsplit(parts._replace(path="/postgres"))
    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        exists = conn.execute(
            "select 1 from pg_database where datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            conn.execute(f'create database "{dbname}"')


_ensure_database_exists(os.environ["TEST_DATABASE_URL"])


@pytest.fixture(scope="session")
def callback_map():
    """Every registered callback, keyed by its outputs.

    Read from the app after one request, because that is when Dash moves
    callbacks out of dash._callback.GLOBAL_CALLBACK_MAP and empties it. A
    test that reads the global map directly sees everything or nothing
    depending on whether an earlier test has made a request.
    """
    import app

    app.server.test_client().get("/")
    return app.app.callback_map


@pytest.fixture(scope="session")
def dash_callback(callback_map):
    """Look up a registered callback by a piece of its output id and return
    the plain function behind it, so a test can call it with the values the
    browser would send. Callbacks declared inside layout builders can only
    be reached this way."""
    def lookup(output_fragment):
        keys = [key for key in callback_map if output_fragment in key]
        assert len(keys) == 1, (output_fragment, keys)
        return callback_map[keys[0]]["callback"].__wrapped__

    return lookup
