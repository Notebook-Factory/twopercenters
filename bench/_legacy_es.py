"""The blob-era Elasticsearch query path, pinned exactly as it read at commit
9261573 (the last commit before 4866222 moved citations_lib.utils onto
Postgres and an authors alias).

citations_lib/utils.py no longer contains this code: get_es_results there now
queries the `authors` alias with a filtered `_source`, and es_result_pick's
`data` branch reads Postgres instead of decompressing a blob. That is
correct for measuring the new stack, but it means bench/latency.py cannot
import a genuine "legacy" implementation from citations_lib.utils any more --
doing so would silently measure the current code twice under two labels.

This module exists so RULING R14's re-measured baseline exercises the actual
old code path (full _source documents, `idx_name` used as a literal ES index
name, base64+zlib blob decompression) against the untouched career/singleyr
indices, not a relabelled copy of the migrated implementation.
"""
import base64
import json
import os
import zlib

import pandas as pd
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

if os.getenv("ELASTICSEARCH_URL"):
    _es = Elasticsearch([os.getenv("ELASTICSEARCH_URL")])
else:
    _es = Elasticsearch([os.getenv("ES_URL_LOCAL")])


def get_es_results(search_term, idx_name, search_fields, exact=False):
    if not search_term:
        return None
    if not exact:
        query = {
            "multi_match": {
                "query": search_term,
                "operator": "and",
                "fuzziness": "auto",
                "fields": search_fields,
            }
        }
    else:
        query = {"term": {search_fields: search_term}}
    result = _es.search(index=idx_name, size=100, body={"query": query})
    hits = result.get("hits", {}).get("hits", [])
    if not hits:
        return None
    return pd.json_normalize(hits)


def _base64_decode_and_decompress(encoded_data, flg=True):
    if flg:
        encoded_data = encoded_data[0]
    compressed_data = base64.b64decode(encoded_data)
    decompressed_data = zlib.decompress(compressed_data)
    return json.loads(decompressed_data.decode("utf-8"))


def es_result_pick(result, field, nohit=[""]):
    if result is None:
        return nohit
    if field == "data":
        return _base64_decode_and_decompress(result[f"_source.{field}"])
    if f"_source.{field}" in result.keys():
        return list(result[f"_source.{field}"])
    return nohit
