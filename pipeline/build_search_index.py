"""Build the slim, blob-free author search index.

Elasticsearch stays in the design because the author typeahead needs its fuzzy
`multi_match` (`citations_lib/utils.py:get_es_results`) to feel
instant while a user is still typing a name. What it must not do any more is
carry the per-author metrics blob: today's `career`/`singleyr` indices store
each author's whole multi-year history zlib-compressed and base64-encoded
under a `data` field mapped as `binary`, a field Elasticsearch can only store
and return, never search or filter on. That is 687 MB (357 + 330) of storage
spent on a field no query touches.

The new document carries exactly what the typeahead queries and what the
dashboard needs to look the metrics up afterwards:

    author_id, authfull, name_normalized, inst_name, cntry, sm_field,
    years_present

`author_id` is the primary key `pages/` uses to fetch the real metrics from
Postgres once the user has picked a name from the dropdown; none of the other
fields are ever displayed on their own, they exist so the typeahead can filter
and rank.

Analyzer choice: `authfull` and `name_normalized` keep the default `text`
mapping (the standard analyzer), matching what the old `elasticSearchIdx.py`
(removed after commit 91102d5) mapped
them as before. `get_es_results` runs `multi_match` with `fuzziness: "auto"`
against `text` fields; changing the analyzer or the field type here would
change what that fuzzy match considers "close enough" and silently degrade
the search Task 2's baseline was measured against. `inst_name`, `cntry` and
`sm_field` stay `text` for the same reason: the aggregate lookups in
`get_es_aggregate` multi_match against them too. `author_id` and
`years_present` are `keyword`: neither is ever fuzzy-matched, both are
exact-match/filter fields (a primary key and a set of edition tags).

`years_present` holds `editions.edition_id` values (e.g. "career-2020",
"singleyr-2020"), not bare years. An author can have a `career` row and a
`singleyr` row for the same data year, and the two are different rows in two
different fact tables joined on `edition_id`, not on year -- collapsing to
plain years would need the dashboard to re-derive which kind(s) that year
covers by re-concatenating strings, inventing a parsing convention where a
correct one already exists as a primary key. Storing `edition_id` verbatim
lets Task 9 use the value directly as the join key against
`career_metrics`/`singleyr_metrics` without reconstructing it.

The alias swap is the other half of the point. `elasticSearchIdx.py` deletes
an index before rebuilding it, so the dashboard sees no results for the
duration of every rebuild. `build()` instead creates a new concrete index,
bulk-loads and refreshes it, then repoints the alias with a single
`indices.update_aliases` call carrying both the "remove old" and "add new"
actions -- that call is atomic on the Elasticsearch side, so a search that
resolves the alias never sees a moment where it points at nothing -- and only
then deletes the old concrete index.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from elasticsearch.helpers import bulk

MAPPING = {
    "properties": {
        "author_id": {"type": "keyword"},
        "authfull": {"type": "text"},
        "name_normalized": {"type": "text"},
        "inst_name": {"type": "text"},
        "cntry": {"type": "text"},
        "sm_field": {"type": "text"},
        "years_present": {"type": "keyword"},
    }
}

# One row per author: authfull/name_normalized come straight from `authors`;
# inst_name/cntry/sm_field come from that author's most recent fact row
# (career or singleyr, whichever has the later observation_date) so the
# typeahead reflects where the author is now, matching the "latest year"
# comment in the legacy `index_es_data`; years_present is every edition_id the
# author has a fact row in, across both kinds.
_AUTHORS_QUERY = """
with unioned as (
    select author_id, edition_id, institution_id, field_id, country_code,
           observation_date
    from career_metrics
    union all
    select author_id, edition_id, institution_id, field_id, country_code,
           observation_date
    from singleyr_metrics
),
ranked as (
    select unioned.*,
           row_number() over (
               partition by author_id order by observation_date desc, edition_id desc
           ) as rn
    from unioned
),
latest as (
    select author_id, institution_id, field_id, country_code
    from ranked
    where rn = 1
),
years as (
    select author_id, array_agg(distinct edition_id order by edition_id) as years_present
    from unioned
    group by author_id
)
select
    a.author_id,
    a.authfull_display as authfull,
    a.name_normalized,
    i.inst_name,
    l.country_code as cntry,
    f.name as sm_field,
    coalesce(y.years_present, '{}') as years_present
from authors a
left join latest l on l.author_id = a.author_id
left join institutions i on i.institution_id = l.institution_id
left join fields f on f.field_id = l.field_id
left join years y on y.author_id = a.author_id
"""


def _new_index_name(alias):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{alias}_{stamp}"


def _sibling_pattern(alias):
    """Regex matching only this alias's own concrete indices.

    A build for `alias` names its indices `f"{alias}_<digits>"`. Matching
    naively on `startswith(f"{alias}_")` would make an `authors` build's
    cleanup sweep pick up `authors_test_<digits>` too, since that string does
    start with `"authors_"`. Anchoring the suffix to digits-only rules that
    out: `authors_test_20260913...` fails `^authors_\\d+$` (its suffix is
    `test_20260913...`, not all digits), so an `authors` sweep can never touch
    an `authors_test` index or vice versa.
    """
    return re.compile(rf"^{re.escape(alias)}_\d+$")


def _orphans(es, alias, keep):
    """Every concrete index belonging to `alias`'s naming scheme except `keep`.

    This is independent of what the alias currently points at, on purpose:
    an index left behind by a run that crashed or was superseded before it
    ever reached the `update_aliases` call is never referenced by the alias,
    so a cleanup step that only looks at `indices.get_alias` can never see it
    and it leaks forever. Enumerating by name pattern instead finds those too.
    """
    pattern = _sibling_pattern(alias)
    all_indices = es.indices.get(index="*")
    return [name for name in all_indices if name != keep and pattern.match(name)]


def _rows(conn):
    with conn.cursor(name="build_search_index") as cur:
        cur.itersize = 5000
        cur.execute(_AUTHORS_QUERY)
        columns = [d.name for d in cur.description]
        for row in cur:
            yield dict(zip(columns, row))


def _actions(conn, index_name):
    for row in _rows(conn):
        yield {
            "_index": index_name,
            "_id": row["author_id"],
            "_source": {
                "author_id": row["author_id"],
                "authfull": row["authfull"],
                "name_normalized": row["name_normalized"],
                "inst_name": row["inst_name"],
                "cntry": row["cntry"],
                "sm_field": row["sm_field"],
                "years_present": list(row["years_present"] or []),
            },
        }


def build(es, conn, alias="authors"):
    """Build a new slim author index and atomically point `alias` at it.

    Returns the concrete index name created. Creates
    `<alias>_<utc timestamp>`, bulk-indexes one document per author (no
    `data` blob), refreshes it, then repoints `alias` with a single
    `indices.update_aliases` call that removes the alias from whatever index
    it previously named and adds it to the new one in the same request, so
    there is no window where the alias resolves to no index.

    Only after that swap succeeds does it sweep away every OTHER concrete
    index matching this alias's own naming scheme (`<alias>_<digits>`), not
    just the one the alias used to point at. That sweep is what reclaims an
    index a previous run built and populated but never got to alias -- a
    crash, an OOM, an interrupted session, a superseded concurrent run --
    which would otherwise never be referenced by anything and leak forever.
    Doing the sweep after, not before, the swap means a failure mid-build
    can never delete the index currently serving traffic.
    """
    new_index = _new_index_name(alias)

    es.indices.create(index=new_index, body={"mappings": MAPPING})
    bulk(es, _actions(conn, new_index))
    es.indices.refresh(index=new_index)

    old_indices = list(es.indices.get_alias(name=alias)) \
        if es.indices.exists_alias(name=alias) else []

    actions = [{"add": {"index": new_index, "alias": alias}}]
    for old_index in old_indices:
        actions.insert(0, {"remove": {"index": old_index, "alias": alias}})
    es.indices.update_aliases(body={"actions": actions})

    for orphan in _orphans(es, alias, new_index):
        es.indices.delete(index=orphan)

    return new_index


if __name__ == "__main__":
    from elasticsearch import Elasticsearch

    from db.connection import connect

    os = __import__("os")
    es_url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
    # The client's default read timeout is 10 seconds, which is a laptop's
    # assumption. On the dokku host every service sits on an attached volume
    # whose flushes take 50 to 140 ms, and Elasticsearch fsyncs its cluster
    # state when an index is created and its translog on the way through a
    # bulk: the create alone timed out there. The work is not lost when that
    # happens, but the run is, and a half-built index is left behind for the
    # next run to sweep up. Retries are on for the same reason: a timeout
    # here means "still busy", not "broken".
    es = Elasticsearch(
        [es_url],
        timeout=int(os.environ.get("ES_TIMEOUT", "120")),
        max_retries=3,
        retry_on_timeout=True,
    )
    with connect() as conn:
        started = datetime.now(timezone.utc)
        index_name = build(es, conn, alias="authors")
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"Built {index_name}, alias 'authors' now points at it. Took {elapsed:.1f}s.")
