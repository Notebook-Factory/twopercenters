"""Single place that resolves the database URL.

dokku sets DATABASE_URL when a Postgres service is linked to the app. Locally it
comes from .env. There is deliberately no hardcoded fallback path: the previous
design's laptop-specific default is the bug this replaces.
"""
import os

import psycopg
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


def dsn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Locally: copy .env.example to .env and "
            "run `make up`. On dokku: `dokku postgres:link <service> <app>`."
        )
    return url


def connect():
    return psycopg.connect(dsn())
