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
