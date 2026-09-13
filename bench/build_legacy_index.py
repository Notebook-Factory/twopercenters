"""Reproduce the blob-era Elasticsearch indexing directly from data_clean/.

elasticSearchIdx.py (unmodified, left alone per the migration plan) built its
`career` and `singleyr` indices from two pickles, composite_career.p and
composite_singleyr.p, that do not exist in this checkout: they were produced
by prep_for_elasticsearch.ipynb from the original qMRLab-clone pickles, in a
directory (/Users/agah/Desktop/neuropoly/no_cite-isfaction) that does not
exist here, and the notebook's committed code has diverged from whatever
version actually produced those pickles (for one, its grouping keys entries
by `sm-field` while labeling the loop variable `authfull`, and it strips
`sm-field` out of the per-year record even though downstream code such as
citations_lib/single_author_layout.py reads `results_career[...]["sm-field"]`
back out of exactly that record -- inconsistent with what the deployed
dashboard actually does at query time).

So this script rebuilds the same *shape* of per-author nested dict directly
from data_clean/, for the four editions the deployed dashboard contains
(versions 1, 2, 3, 5; version 4 is superseded by 5), and indexes it into
Elasticsearch with the same mapping and the same zlib+base64 `data` field
that elasticSearchIdx.py uses. Index names are `career` and `singleyr`,
matching production. Only these two indices are built: the aggregate indices
(career_cntry, career_field, career_inst, singleyr_*) are not touched by the
latency harness and are out of scope for this task.

For each author table, one row becomes one (mergeon -> record) entry, where
mergeon is e.g. "career_2017" for the raw sheet and "career_2017_log" for the
log-transformed copy. The per-author dict is keyed by `authfull` and holds
every edition/year the author appears in, exactly what get_es_results /
es_result_pick / get_auth_years in citations_lib/utils.py expect to read back
out of the `data` field.

Usage:
    python bench/build_legacy_index.py
"""
import base64
import json
import os
import zlib

import numpy as np
import pandas as pd
from dotenv import find_dotenv, load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import parallel_bulk

load_dotenv(find_dotenv())

CLEAN_DIR = os.path.join(os.path.dirname(__file__), "..", "data_clean")

# Same editions, sheets and years prep_for_elasticsearch.ipynb combined, minus
# version 4 (superseded by version 5) and versions 6/7/8 (deployed after the
# dashboard this baseline is measuring).
CAREER_TABLES = [
    (1, "Table-S1-career-2017", 2017),
    (1, "Table-S4-career-2018", 2018),
    (2, "Table-S6-career-2019", 2019),
    (3, "Table_1_Authors_career_2020_wopp_extracted_202108", 2020),
    (5, "Table_1_Authors_career_2021_pubs_since_1788_wopp_extracted_202209b", 2021),
]
SINGLEYR_TABLES = [
    (1, "Table-S2-singleyr-2017", 2017),
    (2, "Table-S7-singleyr-2019", 2019),
    (3, "Table_1_Authors_singleyr_2020_wopp_extracted_202108", 2020),
    (5, "Table_1_Authors_singleyr_2021_pubs_since_1788_wopp_extracted_202209b", 2021),
]

NUMERIC_PRECISION = 3


# ---------------------------------------------------------------------------
# Column standardization -- mechanical renaming, unrelated to the grouping bug
# above. Reproduced from prep_for_elasticsearch.ipynb's standardize_col_names,
# restricted to the v1_present=True branch, which is the only branch the
# notebook ever called.
# ---------------------------------------------------------------------------
def standardize_col_names(df, year, singleyr):
    generic_cols = [
        "authfull", "inst_name", "cntry", "np", "firstyr", "lastyr", "rank (ns)", "nc (ns)",
        "h (ns)", "hm (ns)", "nps (ns)", "ncs (ns)", "cpsf (ns)", "ncsf (ns)", "npsfl (ns)",
        "ncsfl (ns)", "c (ns)", "npciting (ns)", "cprat (ns)", "np cited (ns)", "self%", "rank",
        "nc", "h", "hm", "nps", "ncs", "cpsf", "ncsf", "npsfl", "ncsfl", "c", "npciting", "cprat",
        "np cited", "np_d", "nc_d", "sm-subfield-1", "sm-subfield-1-frac", "sm-subfield-2",
        "sm-subfield-2-frac", "sm-field", "sm-field-frac", "rank sm-subfield-1",
        "rank sm-subfield-1 (ns)", "sm-subfield-1 count",
    ]
    remove_cols = [
        "np cited (ns)", "np cited", "np_d", "nc_d", "rank sm-subfield-1",
        "rank sm-subfield-1 (ns)", "sm-subfield-1 count",
    ]

    if year in (2017, 2018):
        df = df.drop(columns=["sm-1", "sm-2", "sm22"])
        if singleyr and year == 2017:  # singleyr 2017 is missing 2 columns
            remove_cols = remove_cols + ["firstyr", "lastyr"]
        for item in remove_cols:
            generic_cols.remove(item)
        df.columns = generic_cols
    else:
        df.columns = generic_cols
        for item in remove_cols:
            generic_cols.remove(item)
        df = df.drop(columns=remove_cols)
    return df


def round_numeric(value):
    if isinstance(value, float):
        return round(value, NUMERIC_PRECISION)
    return value


def build_composite(tables, singleyr):
    """Build {authfull: {mergeon: {field: value, ...}, ...}, ...}.

    One row -> one (mergeon -> record) entry for that author. mergeon is
    "career_2017", "career_2017_log", etc. This is the same shape
    elasticSearchIdx.py's index_es_data expects: get_all_values_by_key reads
    "cntry"/"inst_name"/"sm-field" back out of the nested per-year records,
    and citations_lib.utils.get_auth_years derives years from the mergeon
    keys.
    """
    composite = {}
    for version, stem, year in tables:
        path = os.path.join(CLEAN_DIR, f"version-{version}", f"{stem}.pkl")
        log_path = os.path.join(CLEAN_DIR, f"version-{version}", f"{stem}_LogTransform.pkl")

        for source_path, mergeon in ((path, f"{'singleyr' if singleyr else 'career'}_{year}"),
                                      (log_path, f"{'singleyr' if singleyr else 'career'}_{year}_log")):
            df = pd.read_pickle(source_path).replace(np.nan, "")
            df = standardize_col_names(df, year, singleyr)
            records = df.to_dict("records")
            for record in records:
                authfull = record["authfull"]
                record = {k: round_numeric(v) for k, v in record.items() if k != "authfull"}
                composite.setdefault(authfull, {})[mergeon] = record

        print(f"  merged   v{version}  {stem[:58]:58}  year={year}")

    return composite


# ---------------------------------------------------------------------------
# Indexing -- mapping and compress_and_base64_encode reproduced verbatim from
# elasticSearchIdx.py (read, not modified, per the migration plan).
# ---------------------------------------------------------------------------
class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)


def compress_and_base64_encode(data):
    json_data = json.dumps(data, cls=NpEncoder)
    compressed_data = zlib.compress(json_data.encode("utf-8"))
    return base64.b64encode(compressed_data).decode("utf-8")


def get_all_values_by_key(data, target_key):
    result = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key == target_key:
                result.append(value)
            elif isinstance(value, (dict, list)):
                result.extend(get_all_values_by_key(value, target_key))
    elif isinstance(data, list):
        for item in data:
            result.extend(get_all_values_by_key(item, target_key))
    return result


def index_es_data(client, df, index_name):
    mappings = {"properties": {
        "authfull": {"type": "text"},
        "cntry": {"type": "text"},
        "inst_name": {"type": "text"},
        "sm-field": {"type": "text"},
        "years": {"type": "text"},
        "data": {"type": "binary"},
    }}

    client.options(ignore_status=[400, 404]).indices.delete(index=index_name)
    client.indices.create(index=index_name, mappings=mappings)

    def doc_generator(df):
        for index, document in enumerate(df):
            yield {
                "_index": index_name,
                "_type": "_doc",
                "_id": index,
                "_source": {
                    "authfull": document,
                    "cntry": list(set(get_all_values_by_key(df[document], "cntry")))[-1],
                    "inst_name": list(set(get_all_values_by_key(df[document], "inst_name")))[-1],
                    "sm-field": list(set(get_all_values_by_key(df[document], "sm-field")))[-1],
                    "years": list(set([cr.split("_")[1] for cr in list(df[document].keys())])),
                    "data": compress_and_base64_encode(df[document]),
                },
            }

    for success, info in parallel_bulk(client, doc_generator(df), raise_on_error=False):
        if not success:
            print("A document failed:", info)

    client.indices.refresh(index=index_name)
    print(f"Done {index_name}")


def get_client():
    if os.getenv("ELASTICSEARCH_URL"):
        return Elasticsearch([os.getenv("ELASTICSEARCH_URL")])
    return Elasticsearch([os.getenv("ES_URL_LOCAL")])


def main():
    client = get_client()

    print("Building career composite from data_clean/ (versions 1, 2, 3, 5)...")
    career = build_composite(CAREER_TABLES, singleyr=False)
    print(f"  {len(career)} authors")
    index_es_data(client, career, "career")

    print("Building singleyr composite from data_clean/ (versions 1, 2, 3, 5)...")
    singleyr = build_composite(SINGLEYR_TABLES, singleyr=True)
    print(f"  {len(singleyr)} authors")
    index_es_data(client, singleyr, "singleyr")


if __name__ == "__main__":
    main()
