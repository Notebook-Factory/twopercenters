import os
from elasticsearch import Elasticsearch
import psycopg
from pipeline.build_search_index import build

ES = Elasticsearch([os.environ["ELASTICSEARCH_URL"]])


def test_documents_carry_no_blob():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        build(ES, conn, alias="authors_test")
    hit = ES.search(index="authors_test", size=1)["hits"]["hits"][0]["_source"]
    assert "data" not in hit
    assert set(hit) == {"author_id", "authfull", "name_normalized",
                        "inst_name", "cntry", "sm_field", "years_present"}


def test_alias_swap_leaves_exactly_one_index():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        first = build(ES, conn, alias="authors_test")
        second = build(ES, conn, alias="authors_test")
    assert first != second
    assert set(ES.indices.get_alias(name="authors_test")) == {second}
    assert not ES.indices.exists(index=first)


def test_orphaned_index_from_a_prior_failed_run_is_swept_up():
    """A run that built and populated an index but crashed before the
    alias swap leaves a concrete index the alias never pointed at. Nothing
    in `old_indices` (derived from `indices.get_alias`) can see that index,
    so a build must find it by naming pattern instead, or it leaks forever.
    """
    orphan = "authors_test_000000000000000001"
    ES.indices.create(index=orphan, body={"mappings": {
        "properties": {"author_id": {"type": "keyword"}}}})
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            build(ES, conn, alias="authors_test")
        assert not ES.indices.exists(index=orphan)
    finally:
        if ES.indices.exists(index=orphan):
            ES.indices.delete(index=orphan)


def test_build_never_touches_an_index_belonging_to_another_alias():
    """`authors_test_<digits>` is a prefix-match of `authors_<digits>` under a
    naive `startswith`. A build for `authors_test` must not delete an index
    that belongs to the (unrelated) `authors` naming scheme, and vice versa.
    """
    other_alias_index = "authors_000000000000000002"
    ES.indices.create(index=other_alias_index, body={"mappings": {
        "properties": {"author_id": {"type": "keyword"}}}})
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            build(ES, conn, alias="authors_test")
        assert ES.indices.exists(index=other_alias_index)
        assert set(ES.indices.get_alias(name="authors_test")) != {other_alias_index}
    finally:
        ES.indices.delete(index=other_alias_index)


def test_repeated_builds_leave_exactly_one_index_even_with_an_orphan_present():
    orphan = "authors_test_000000000000000003"
    ES.indices.create(index=orphan, body={"mappings": {
        "properties": {"author_id": {"type": "keyword"}}}})
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            current = build(ES, conn, alias="authors_test")
        assert set(ES.indices.get_alias(name="authors_test")) == {current}
        assert not ES.indices.exists(index=orphan)
    finally:
        if ES.indices.exists(index=orphan):
            ES.indices.delete(index=orphan)
