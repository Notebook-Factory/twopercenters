"""Turn the RelBench dataset into a materialized heterogeneous graph.

``make_pkey_fkey_graph`` reads the foreign keys as edges and encodes each
table's columns according to a semantic-type dictionary. That dictionary is
the thing worth being careful about: RelBench proposes types from simple
heuristics over dtype and cardinality, and two of its guesses would be wrong
here in ways that never raise.

``firstyr`` and ``lastyr`` are years. There are only about sixty distinct
values, so the heuristic labels them categorical, which would turn a
regression over them into a sixty-way classification and throw away the fact
that 1994 is between 1993 and 1995.

The identity columns are handled by dropping them in ``rdl.spec`` rather than
by typing them here, so they never reach this module at all. See the comment
on the authors table there.

Encoding is cached: materialization is slow and every task repeats it.
"""
from __future__ import annotations

import argparse
import logging
import resource
from pathlib import Path
from typing import Any

from rdl import spec

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "data_rdl" / "twopercenters"
CACHE_DIR = ROOT / "data_rdl" / "cache"


def apply_pins(proposed: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Overlay our declared semantic types on RelBench's proposal.

    Columns declared in ``drop_columns`` are removed outright. Columns
    declared in ``stypes`` take our value. Everything else keeps whatever was
    proposed, so a column we have not thought about still gets a sensible
    default rather than disappearing.
    """
    from torch_frame import stype as ST

    out: dict[str, dict[str, Any]] = {}
    for table, cols in proposed.items():
        table_spec = spec.TABLES.get(table)
        merged: dict[str, Any] = {}
        for col, proposed_stype in cols.items():
            if table_spec is not None and col in table_spec.drop_columns:
                continue
            if table_spec is not None and col in table_spec.stypes:
                pinned = ST[table_spec.stypes[col]]
                if str(pinned) != str(proposed_stype):
                    logger.info("%s.%s: pinned %s over proposed %s",
                                table, col, pinned, proposed_stype)
                merged[col] = pinned
            else:
                merged[col] = proposed_stype
        out[table] = merged
    return out


def stype_dict(db) -> dict[str, dict[str, Any]]:
    from relbench.modeling.utils import get_stype_proposal

    return apply_pins(get_stype_proposal(db))


def build(dataset_dir: Path = DATASET_DIR,
          cache_dir: Path | None = CACHE_DIR,
          upto_test_timestamp: bool = True):
    """Materialize the graph. Returns (HeteroData, col_stats_dict)."""
    from relbench.load import load_dataset
    from relbench.modeling.graph import make_pkey_fkey_graph

    dataset = load_dataset(str(dataset_dir))
    db = dataset.get_db(upto_test_timestamp=upto_test_timestamp)
    col_to_stype = stype_dict(db)

    data, col_stats = make_pkey_fkey_graph(
        db,
        col_to_stype_dict=col_to_stype,
        # No text_embedder_cfg: rdl.spec drops every text column, so none is
        # needed. If a text column is ever reintroduced this call will raise
        # rather than silently skip it.
        cache_dir=str(cache_dir) if cache_dir else None,
    )
    return data, col_stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default=str(CACHE_DIR))
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(message)s")

    data, col_stats = build(cache_dir=None if args.no_cache else Path(args.cache))

    print()
    print("node types")
    for node_type in data.node_types:
        store = data[node_type]
        n = store.num_nodes
        cols = len(col_stats.get(node_type, {}))
        print(f"  {node_type:16s} nodes={n:9d} encoded_columns={cols}")
    print("edge types")
    for edge_type in data.edge_types:
        src, rel, dst = edge_type
        print(f"  {src} -{rel}-> {dst}: {data[edge_type].num_edges:9d} edges")

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9
    print()
    print(f"peak RSS: {peak:.2f} GB")


if __name__ == "__main__":
    main()
