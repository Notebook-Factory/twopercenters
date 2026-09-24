"""Fill career_metrics.list_position and its self-citation-excluded twin.

Position on the published list, which is what `rank` is not: `rank` counts
every scientist Scopus scored, this counts only the ones who made the edition.

Run after loading a new edition. One statement per edition per column, each in
its own transaction, because the whole job rewrites 2.7 million rows and takes
about eight minutes: doing it in a single transaction once meant that hitting a
timeout threw away every edition already finished.

Safe to re-run. By default it does only the editions with a null position,
which is what a newly loaded edition looks like; --all recomputes everything,
which is what a change to the ordering would need.
"""
from __future__ import annotations

import argparse
import logging
import time

logger = logging.getLogger(__name__)

TABLES = ("career_metrics", "singleyr_metrics")
# (column to fill, score to order by, rank that breaks ties)
COLUMNS = (("list_position", "c", "rank"),
           ("list_position_ns", "c_ns", "rank_ns"))


def editions_needing(conn, table: str, column: str, everything: bool) -> list[str]:
    if everything:
        sql = f"select distinct edition_id from {table} order by 1"
    else:
        sql = (f"select edition_id from {table} "
               f"where {column} is null group by edition_id order by 1")
    return [row[0] for row in conn.execute(sql).fetchall()]


def fill(conn, table: str, column: str, score: str, tiebreak: str,
         edition_id: str) -> int:
    # Ordered by the composite score with the published rank breaking ties,
    # which is the publishers' own ordering: sorting an edition by score leaves
    # rank increasing at every step bar a handful.
    cursor = conn.execute(
        f"""
        update {table} m set {column} = s.pos
        from (select metric_id,
                     row_number() over (order by {score} desc, {tiebreak}) pos
              from {table} where edition_id = %s) s
        where s.metric_id = m.metric_id and m.edition_id = %s
        """, (edition_id, edition_id))
    return cursor.rowcount


def record_size(conn, edition_id: str, rows: int) -> None:
    """Keep editions.published_rows in step with what was just counted.

    Every position needs this denominator and counting it live costs well over
    a second, which used to land on the first reader of each web worker.
    """
    conn.execute("update editions set published_rows = %s where edition_id = %s",
                 (rows, edition_id))


def run(conn, everything: bool = False) -> int:
    total = 0
    for table in TABLES:
        for column, score, tiebreak in COLUMNS:
            for edition_id in editions_needing(conn, table, column, everything):
                started = time.time()
                rows = fill(conn, table, column, score, tiebreak, edition_id)
                record_size(conn, edition_id, rows)
                conn.commit()
                total += rows
                logger.info("%s.%s %s: %d rows in %.1fs",
                            table, column, edition_id, rows,
                            time.time() - started)
    return total


def main() -> None:
    from db.connection import connect

    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true",
                        help="recompute every edition, not only unfilled ones")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with connect() as conn:
        print(f"{run(conn, everything=args.all):,} rows written")


if __name__ == "__main__":
    main()
