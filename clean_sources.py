"""Reproduce code_test_preproc/01_data_pickling.ipynb over every dataset edition.

For each author table in data_raw/ this writes two pickles into data_clean/:
the sheet exactly as read, and a copy where every numeric column has been
rescaled to log(x+1)/log(max+1) against that column's own maximum.

The behaviour is deliberately identical to the original notebook, including
details that are arguably wrong: the log transform is applied to rank, firstyr
and lastyr as well as to the citation metrics, and the maximum comes from the
data rather than from the Table_3_maxlog_* files the publishers ship. Changing
either would break comparison with the pickles committed upstream, which is how
verify_clean.py demonstrates that this reimplementation is faithful.

Usage:
    clean_sources.py <data_raw_dir> <data_clean_dir> [--include-superseded]
"""
import argparse
import glob
import json
import os
import re
import time

import numpy as np
import pandas as pd
from openpyxl import load_workbook

# Version 4 is the uncorrected 2021 release; version 5 replaces it.
SUPERSEDED_VERSIONS = {4}


def find_author_tables(raw_dir, include_superseded):
    """Author tables are the workbooks holding a Key sheet and exactly one other.

    The companion files (field/subfield thresholds, maxlog tables, Table-S3,
    Table-S5) have no Key sheet, so this distinguishes them without hardcoding
    filenames the way the original notebook did.
    """
    tables = []
    for path in sorted(glob.glob(os.path.join(raw_dir, "version-*", "*.xlsx"))):
        version = int(re.search(r"version-(\d+)", path).group(1))
        if version in SUPERSEDED_VERSIONS and not include_superseded:
            continue
        workbook = load_workbook(path, read_only=True)
        sheets = workbook.sheetnames
        workbook.close()
        if "Key" in sheets and len(sheets) == 2:
            data_sheet = next(s for s in sheets if s != "Key")
            tables.append((version, path, data_sheet))
    return tables


def log_transform(df):
    """Rescale every float64/int64 column, in place, as the notebook did."""
    metrics = [c for c in df.columns if df[c].dtype in ("float64", "int64")]
    for col in metrics:
        df.loc[:, col] = np.log(df[col] + 1) / np.log(df[col].max() + 1)
    return df


def write_key(path, data_sheet, destination):
    """Save the workbook's Key sheet, the publishers' own data dictionary."""
    workbook = load_workbook(path, read_only=True)
    rows = [
        [None if c is None else str(c) for c in row]
        for row in workbook["Key"].iter_rows(values_only=True)
        if any(c is not None for c in row)
    ]
    workbook.close()
    header, body = rows[0], rows[1:]
    entries = [dict(zip(header, r)) for r in body]
    json.dump({"source": os.path.basename(path), "data_sheet": data_sheet,
               "fields": entries}, open(destination, "w"), indent=1)


parser = argparse.ArgumentParser()
parser.add_argument("raw_dir")
parser.add_argument("clean_dir")
parser.add_argument("--include-superseded", action="store_true",
                    help="also process version 4, which version 5 replaces")
args = parser.parse_args()

tables = find_author_tables(args.raw_dir, args.include_superseded)
print(f"{len(tables)} author tables to process\n")

done = skipped = 0
for version, path, data_sheet in tables:
    stem = os.path.splitext(os.path.basename(path))[0]
    out_dir = os.path.join(args.clean_dir, f"version-{version}")
    os.makedirs(out_dir, exist_ok=True)
    raw_out = os.path.join(out_dir, f"{stem}.pkl")
    log_out = os.path.join(out_dir, f"{stem}_LogTransform.pkl")

    if os.path.exists(raw_out) and os.path.exists(log_out):
        print(f"  skip      v{version}  {stem[:58]}")
        skipped += 1
        continue

    started = time.time()
    print(f"  reading   v{version}  {stem[:58]}", flush=True)
    df = pd.read_excel(path, sheet_name=data_sheet)
    df.to_pickle(raw_out)
    log_transform(df).to_pickle(log_out)
    write_key(path, data_sheet, os.path.join(out_dir, f"{stem}_key.json"))
    done += 1
    print(f"    {df.shape[0]:,} rows x {df.shape[1]} cols in {time.time() - started:.0f}s", flush=True)

print(f"\nDONE  processed={done}  skipped={skipped}")
