"""Shared pytest setup.

pytest does not load .env on its own, and the test modules read
os.environ["DATABASE_URL"] / os.environ["ELASTICSEARCH_URL"] directly. This
file loads .env first (if present) so a real value there wins, and then fills
in the same local defaults as .env.example for anything still unset, so the
test suite works out of the box against the docker-compose services.
"""
import os

from dotenv import load_dotenv

load_dotenv()

_DEFAULTS = {
    "DATABASE_URL": "postgresql://twopct:twopct@localhost:5433/twopct",
    "ELASTICSEARCH_URL": "http://localhost:9201",
}

for _key, _value in _DEFAULTS.items():
    os.environ.setdefault(_key, _value)
