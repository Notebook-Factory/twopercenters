"""Turn the Parquet export into a RelBench dataset directory.

RelBench's key contract is strict and it is checked. ``Dataset.validate_and_
correct_db`` raises unless every table's primary key is exactly ``0..n-1`` in
row order, and it treats foreign keys as integer positions into the
destination table, nulling anything at or beyond its length. Our keys are
strings (``author_id``, ``edition_id``, ``country_code``) or a non-contiguous
integer (``metric_id``), so every one of them has to be remapped.

The remapping happens once, here, before any task labels exist. Doing it the
other way round is the classic way to end up with labels keyed to one
indexing and a graph keyed to another, which produces a model that trains
happily on nonsense.

Three rules, each of which has a test:

1. Fact tables are sorted by their time column before indices are assigned,
   so the integer key is monotonic in time and the split boundaries stay
   contiguous. Ties break on the original key so two builds agree byte for
   byte.
2. A foreign key that does not resolve becomes NULL, never 0. Mapping an
   unknown value to 0 would quietly attribute those rows to whichever entity
   sorts first.
3. Every table gets a key map written beside it. Without one, a prediction
   for entity 4471 can never be turned back into a person's name, which is
   the entire point of showing it to anyone.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from rdl import spec

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PARQUET_DIR = ROOT / "data_parquet"
DATASET_DIR = ROOT / "data_rdl" / "twopercenters"


@dataclass(frozen=True)
class Reindexable:
    """The part of a table spec that reindexing needs."""

    pkey: str | None
    time_col: str | None = None
    fkeys: dict[str, str] = field(default_factory=dict)


def specs_from_spec() -> dict[str, Reindexable]:
    return {
        name: Reindexable(pkey=t.pkey, time_col=t.time_col, fkeys=dict(t.fkeys))
        for name, t in spec.TABLES.items()
    }


def _ordered(df: pd.DataFrame, s: Reindexable) -> pd.DataFrame:
    """Put a table into the row order its integer keys will follow."""
    if s.time_col and s.time_col in df.columns:
        by = [s.time_col, s.pkey]
    else:
        by = [s.pkey]
    return df.sort_values(by, kind="mergesort").reset_index(drop=True)


def reindex(
    frames: dict[str, pd.DataFrame],
    specs: dict[str, Reindexable],
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Remap every primary and foreign key to a consecutive integer.

    Returns the rewritten frames and, per table, a two-column key map of
    ``original`` to ``index``.
    """
    ordered: dict[str, pd.DataFrame] = {}
    keymaps: dict[str, pd.DataFrame] = {}

    # Pass one: order each table and mint its new keys.
    for name, df in frames.items():
        s = specs[name]
        if s.pkey is None:
            ordered[name] = df.reset_index(drop=True)
            continue

        if df[s.pkey].duplicated().any():
            dupes = df.loc[df[s.pkey].duplicated(), s.pkey].unique()[:3]
            raise ValueError(
                f"{name}.{s.pkey} has duplicate values (e.g. {list(dupes)}). "
                f"The key map would be ambiguous and rows would be dropped.")

        out = _ordered(df, s)
        keymaps[name] = pd.DataFrame({
            "original": out[s.pkey].to_numpy(),
            "index": range(len(out)),
        })
        ordered[name] = out

    # Pass two: rewrite the keys. Done after pass one so that a foreign key
    # can be resolved against a destination table's finished map regardless
    # of the order tables happen to be processed in.
    lookups = {
        name: dict(zip(km["original"], km["index"]))
        for name, km in keymaps.items()
    }

    result: dict[str, pd.DataFrame] = {}
    for name, df in ordered.items():
        s = specs[name]
        out = df.copy()

        for fkey_col, dest in s.fkeys.items():
            if fkey_col not in out.columns:
                continue
            lookup = lookups[dest]
            mapped = out[fkey_col].map(lookup)
            unresolved = mapped.isna() & out[fkey_col].notna()
            if unresolved.any():
                sample = out.loc[unresolved, fkey_col].unique()[:3]
                logger.warning(
                    "%s.%s -> %s: %d value(s) do not resolve and become NULL "
                    "(e.g. %s)", name, fkey_col, dest, int(unresolved.sum()),
                    list(sample))
            # Nullable integer: a dangling key must stay missing, and a plain
            # int64 column cannot hold NA.
            out[fkey_col] = mapped.astype("Int64")

        if s.pkey is not None:
            out[s.pkey] = pd.Series(range(len(out)), dtype="int64")

        result[name] = out

    return result, keymaps


def load_frames() -> dict[str, pd.DataFrame]:
    """Read the exported Parquet, apply the declared drops, keep career."""
    frames: dict[str, pd.DataFrame] = {}
    for name, t in spec.TABLES.items():
        df = pd.read_parquet(PARQUET_DIR / f"{name}.parquet")
        drops = [c for c in t.drop_columns if c in df.columns]
        if drops:
            df = df.drop(columns=drops)
        if name == "editions":
            # Only the career editions are in this graph. Leaving the seven
            # singleyr editions in would put nodes in the graph that no fact
            # row references.
            df = df[df["kind"] == "career"].reset_index(drop=True)
        frames[name] = df
        logger.info("loaded %s: %d rows, %d columns",
                    name, len(df), df.shape[1])
    return frames


def build(out_dir: Path = DATASET_DIR) -> Path:
    from relbench.manifest import DatasetManifest
    from relbench.manifest import TableSpec as RBTableSpec

    frames = load_frames()
    reindexed, keymaps = reindex(frames, specs_from_spec())

    db_dir = out_dir / "db"
    key_dir = out_dir / "keymap"
    db_dir.mkdir(parents=True, exist_ok=True)
    key_dir.mkdir(parents=True, exist_ok=True)

    for name, df in reindexed.items():
        df.to_parquet(db_dir / f"{name}.parquet", index=False)
    for name, km in keymaps.items():
        km.to_parquet(key_dir / f"{name}.parquet", index=False)

    manifest = DatasetManifest(
        name="twopercenters",
        description=(
            "Ioannidis/Elsevier top-2% of scientists, career editions 2017 "
            "to 2024, normalised from the published spreadsheets into a "
            "relational schema."
        ),
        val_timestamp=str(spec.VAL_TIMESTAMP.date()),
        test_timestamp=str(spec.TEST_TIMESTAMP.date()),
        tables={
            name: RBTableSpec(pkey=t.pkey, time_col=t.time_col,
                              fkeys=dict(t.fkeys))
            for name, t in spec.TABLES.items()
        },
    )
    manifest.save(out_dir / "manifest.yaml")
    logger.info("wrote dataset to %s", out_dir)
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DATASET_DIR))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(message)s")
    build(Path(args.out))


if __name__ == "__main__":
    main()
