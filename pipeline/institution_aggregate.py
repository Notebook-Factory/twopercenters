"""Live institution aggregate for the group_metrics dashboard interface.

RULING R21: a fully materialised group_metrics view covering country, field
AND institution measured out to 7,412,496 rows / 1,651 MB, of which
institution accounted for 7,344,948 rows (99.1 percent) and essentially all
the disk space, and refreshing it ran for 45 minutes holding an ACCESS
EXCLUSIVE lock -- unacceptable on a box that also hosts five other
dashboards. A lookup for a single institution is cheap by comparison:
career_metrics_cntry_idx and singleyr_metrics_cntry_idx are both
(institution_id, edition_id), so filtering to one institution touches only
that institution's rows across all editions, not the whole table.

db/migrations/005_group_metrics_narrow.sql therefore only materialises
group_kind IN ('cntry', 'sm-field'). This module answers group_kind
'inst_name' the same way, computed live, so that the dashboard-facing
behaviour behind get_es_aggregate('inst_name', name, prefix) is unchanged:
Task 9 calls institution_aggregate_by_name() for that case and gets back rows
shaped exactly like group_metrics (edition_id, group_kind, group_value,
metric, min, q1, median, q3, max, n).

Metric coverage matches process_data_by_country
(code_test_preproc/02_data_preproc_for_speed.ipynb): the 12 base metrics, the
same 12 with the _ns suffix, plus np and self_pct -- 26 in total, same list
used by 004/005_group_metrics*.sql.
"""
from __future__ import annotations

BASE_METRICS = ["rank", "c", "nc", "h", "hm", "ncs", "ncsf", "ncsfl", "nps",
                "cpsf", "npsfl", "npciting"]
METRICS = BASE_METRICS + [f"{m}_ns" for m in BASE_METRICS] + ["np", "self_pct"]

_TABLE_BY_KIND = {"career": "career_metrics", "singleyr": "singleyr_metrics"}


def _wide_query(table):
    cols = []
    for m in METRICS:
        cols.append(f"min({m}) as {m}_min")
        cols.append(
            f"percentile_cont(0.25) within group (order by {m}::double precision) as {m}_q1")
        cols.append(
            f"percentile_cont(0.5) within group (order by {m}::double precision) as {m}_median")
        cols.append(
            f"percentile_cont(0.75) within group (order by {m}::double precision) as {m}_q3")
        cols.append(f"max({m}) as {m}_max")
        cols.append(f"count({m}) as {m}_n")
    return (
        f"select edition_id, {', '.join(cols)} "
        f"from {table} where institution_id = %s "
        f"group by edition_id"
    )


def institution_aggregate(conn, institution_id, kind):
    """Return group_metrics-shaped rows for one institution_id, computed live.

    `kind` is 'career' or 'singleyr' (editions.kind / the dashboard's
    `prefix`). Returns a list of
    (edition_id, group_kind, group_value, metric, min, q1, median, q3, max, n)
    tuples, one per (edition, metric) -- the same shape as a row of
    group_metrics, with group_kind fixed to 'inst_name'.
    """
    table = _TABLE_BY_KIND[kind]

    row = conn.execute(
        "select inst_name from institutions where institution_id = %s",
        (institution_id,)).fetchone()
    if row is None:
        return []
    inst_name = row[0]

    cur = conn.execute(_wide_query(table), (institution_id,))
    out = []
    for wide_row in cur.fetchall():
        edition_id = wide_row[0]
        for i, metric in enumerate(METRICS):
            base = 1 + i * 6
            mn, q1, median, q3, mx, n = wide_row[base:base + 6]
            out.append((edition_id, "inst_name", inst_name, metric,
                        mn, q1, median, q3, mx, n))
    return out


def institution_aggregate_by_name(conn, inst_name, kind):
    """Same as institution_aggregate(), looked up by inst_name (exact match)
    -- the form get_es_aggregate('inst_name', group_name, prefix) has on hand.
    """
    row = conn.execute(
        "select institution_id from institutions where inst_name = %s",
        (inst_name,)).fetchone()
    if row is None:
        return []
    return institution_aggregate(conn, row[0], kind)
