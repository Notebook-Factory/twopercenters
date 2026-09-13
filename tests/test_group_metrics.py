"""Tests for the group_metrics materialized view
(db/migrations/004_group_metrics.sql, narrowed by
db/migrations/005_group_metrics_narrow.sql) and the live institution
aggregate (pipeline/institution_aggregate.py).

RULING R21: a fully materialised view covering country, field AND
institution measured 7,412,496 rows / 1,651 MB, and its refresh ran for 45
minutes holding an ACCESS EXCLUSIVE lock. group_metrics now only
materialises group_kind IN ('cntry', 'sm-field'); institution is served live
via pipeline/institution_aggregate.py. Together the three still answer every
group_kind get_es_aggregate needs -- these tests check both halves.

These connect to the already-migrated, already-loaded database (see
tests/conftest.py for DATABASE_URL). Rebuilding the database from scratch takes
about eight minutes and is deliberately not done here.
"""
import os
import time

import psycopg

from pipeline.institution_aggregate import (
    METRICS,
    institution_aggregate_by_name,
)

DSN = os.environ["DATABASE_URL"]


def test_group_metrics_materialises_country_and_field_only():
    """RULING R21 narrowed the materialised view to these two kinds;
    institution is answered live (see the institution_aggregate tests below)."""
    with psycopg.connect(DSN) as conn:
        kinds = {r[0] for r in conn.execute(
            "select distinct group_kind from group_metrics").fetchall()}
        assert kinds == {"cntry", "sm-field"}


def test_quartiles_are_ordered():
    with psycopg.connect(DSN) as conn:
        bad = conn.execute(
            "select count(*) from group_metrics "
            "where not (min <= q1 and q1 <= median "
            "and median <= q3 and q3 <= max)").fetchone()[0]
        assert bad == 0


def test_reachable_by_career_and_singleyr_prefix():
    """group_name -> edition_id -> editions.kind must reach both prefixes
    the dashboard uses ('career' and 'singleyr')."""
    with psycopg.connect(DSN) as conn:
        kinds = {r[0] for r in conn.execute(
            "select distinct e.kind from group_metrics gm "
            "join editions e on e.edition_id = gm.edition_id").fetchall()}
        assert kinds == {"career", "singleyr"}


def test_covers_the_26_metrics_the_notebook_computed():
    """process_data_by_country covered 12 metrics, their _ns counterparts,
    plus np and self_pct -- 26 in total."""
    base = ["rank", "c", "nc", "h", "hm", "ncs", "ncsf", "ncsfl", "nps",
            "cpsf", "npsfl", "npciting"]
    expected = set(base) | {f"{m}_ns" for m in base} | {"np", "self_pct"}
    assert set(METRICS) == expected
    with psycopg.connect(DSN) as conn:
        got = {r[0] for r in conn.execute(
            "select distinct metric from group_metrics").fetchall()}
        assert got == expected


def test_no_null_group_values():
    with psycopg.connect(DSN) as conn:
        n = conn.execute(
            "select count(*) from group_metrics where group_value is null"
        ).fetchone()[0]
        assert n == 0


def test_n_matches_actual_non_null_count_for_a_sample_field_metric():
    """Spot-check: n for one (edition, field, metric) row must equal a
    direct count of non-null values in career_metrics for that group."""
    with psycopg.connect(DSN) as conn:
        row = conn.execute(
            "select gm.edition_id, f.field_id, gm.n "
            "from group_metrics gm "
            "join fields f on f.name = gm.group_value "
            "join editions e on e.edition_id = gm.edition_id "
            "where gm.group_kind = 'sm-field' and gm.metric = 'nc' "
            "and e.kind = 'career' "
            "limit 1").fetchone()
        assert row is not None
        edition_id, field_id, n = row
        actual = conn.execute(
            "select count(*) from career_metrics "
            "where edition_id = %s and field_id = %s and nc is not null",
            (edition_id, field_id)).fetchone()[0]
        assert n == actual


# --- live institution aggregate (RULING R21's replacement for a
# materialised 'inst_name' grouping) ---

def _a_populated_institution_name(conn):
    row = conn.execute(
        "select i.inst_name from institutions i "
        "join career_metrics cm on cm.institution_id = i.institution_id "
        "limit 1").fetchone()
    assert row is not None
    return row[0]


def test_institution_aggregate_covers_all_three_group_kinds_with_group_metrics():
    """Together, group_metrics (cntry, sm-field) and institution_aggregate_by_name
    (inst_name) answer every group_kind get_es_aggregate needs."""
    with psycopg.connect(DSN) as conn:
        inst_name = _a_populated_institution_name(conn)
        rows = institution_aggregate_by_name(conn, inst_name, "career")
        assert rows
        assert {r[1] for r in rows} == {"inst_name"}
        assert {r[2] for r in rows} == {inst_name}


def test_institution_aggregate_quartiles_are_ordered():
    with psycopg.connect(DSN) as conn:
        inst_name = _a_populated_institution_name(conn)
        rows = institution_aggregate_by_name(conn, inst_name, "career")
        for edition_id, group_kind, group_value, metric, mn, q1, median, q3, mx, n in rows:
            if n == 0:
                continue
            assert mn <= q1 <= median <= q3 <= mx, (edition_id, metric)


def test_institution_aggregate_covers_the_26_metrics():
    with psycopg.connect(DSN) as conn:
        inst_name = _a_populated_institution_name(conn)
        rows = institution_aggregate_by_name(conn, inst_name, "career")
        got = {r[3] for r in rows}
        assert got == set(METRICS)


def test_institution_aggregate_matches_direct_count():
    """Spot-check the live aggregate against a direct count over
    career_metrics, the same way test_n_matches_actual_non_null_count_for_a_sample_field_metric
    checks the materialised view."""
    with psycopg.connect(DSN) as conn:
        institution_id, inst_name = conn.execute(
            "select i.institution_id, i.inst_name from institutions i "
            "join career_metrics cm on cm.institution_id = i.institution_id "
            "limit 1").fetchone()
        rows = institution_aggregate_by_name(conn, inst_name, "career")
        one_edition_nc = [r for r in rows if r[3] == "nc"][0]
        edition_id = one_edition_nc[0]
        actual = conn.execute(
            "select count(*) from career_metrics "
            "where edition_id = %s and institution_id = %s and nc is not null",
            (edition_id, institution_id)).fetchone()[0]
        assert one_edition_nc[9] == actual


def test_institution_aggregate_is_fast():
    """A single institution lookup must not resemble a full-table scan --
    this is the whole justification for RULING R21 (institution touches its
    own index-selected rows, not the multi-million-row fact tables)."""
    with psycopg.connect(DSN) as conn:
        inst_name = _a_populated_institution_name(conn)
        start = time.perf_counter()
        rows = institution_aggregate_by_name(conn, inst_name, "career")
        elapsed = time.perf_counter() - start
        assert rows
        assert elapsed < 1.0, f"took {elapsed:.3f}s, expected a sub-second indexed lookup"
