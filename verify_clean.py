"""Compare pickles produced by clean_sources.py against the originals.

The qMRLab/no_cite-isfaction repository committed the pickles that the original
notebook produced for versions 1, 2, 3 and 5. Those nine tables are the only
independent check we have that the reimplementation is faithful, so this script
compares them cell by cell.

Integers, strings and NaN positions must match exactly. Floats are allowed to
differ by a couple of units in the last place, because the log transform calls
np.log and different numpy builds take different vectorized paths through it.
Measured against the committed pickles, 872 of 7,799,196 float cells differ and
the worst is 2 ULP, which is rounding, not arithmetic. Requiring bit-identical
np.log output across numpy versions is not a property any implementation can
promise, so the tolerance is stated here rather than left implicit.

Usage:
    verify_clean.py <data_clean_dir> <reference_repo_dir> [--max-ulp N]
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("clean_dir")
parser.add_argument("reference_repo")
parser.add_argument("--max-ulp", type=int, default=4,
                    help="float cells may differ by up to this many units in the "
                         "last place (default 4); integers and strings must match exactly")
args = parser.parse_args()

CLEAN = args.clean_dir
REFERENCE = args.reference_repo

# Versions for which upstream committed the original pickles.
VERIFIABLE_VERSIONS = [1, 2, 3, 5]


def ulp_distance(a, b):
    """How many representable doubles apart two float arrays are, elementwise."""
    return np.abs(a.view(np.int64) - b.view(np.int64))


def differences(new, ref):
    """Return (problems, worst_ulp) comparing two dataframes."""
    problems = []
    worst_ulp = 0

    if new.shape != ref.shape:
        problems.append(f"shape {new.shape} != {ref.shape}")
        return problems, worst_ulp

    if list(new.columns) != list(ref.columns):
        only_new = [c for c in new.columns if c not in ref.columns]
        only_ref = [c for c in ref.columns if c not in new.columns]
        if only_new or only_ref:
            problems.append(f"columns differ: only in new {only_new}, only in reference {only_ref}")
        else:
            problems.append("column order differs")
        return problems, worst_ulp

    if new.equals(ref):
        return problems, worst_ulp

    for col in new.columns:
        a, b = new[col], ref[col]

        if a.dtype != b.dtype:
            problems.append(f"[{col}] dtype {a.dtype} != {b.dtype}")

        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            if not (a.isna() == b.isna()).all():
                problems.append(f"[{col}] NaN positions differ")
                continue

            if pd.api.types.is_float_dtype(a):
                x, y = a.to_numpy(), b.to_numpy()
                present = ~(np.isnan(x) & np.isnan(y))
                x, y = x[present], y[present]
                unequal = x != y
                if unequal.any():
                    ulp = ulp_distance(x[unequal], y[unequal]).max()
                    worst_ulp = max(worst_ulp, int(ulp))
                    if ulp > args.max_ulp:
                        problems.append(
                            f"[{col}] differs by up to {ulp} ULP over "
                            f"{unequal.sum()} of {len(x)} values"
                        )
            else:
                unequal = (a != b).fillna(False)
                if unequal.any():
                    problems.append(
                        f"[{col}] {unequal.sum()} integer values differ, first example "
                        f"new={a[unequal].head(1).tolist()} reference={b[unequal].head(1).tolist()}"
                    )
        else:
            unequal = ~((a == b) | (a.isna() & b.isna()))
            if unequal.any():
                example = a[unequal].head(1).tolist(), b[unequal].head(1).tolist()
                problems.append(
                    f"[{col}] {unequal.sum()} values differ, first example "
                    f"new={example[0]} reference={example[1]}"
                )

    return problems, worst_ulp


checked = passed = 0
failures = []

for version in VERIFIABLE_VERSIONS:
    ref_dir = os.path.join(REFERENCE, "data", f"version-{version}")
    clean_dir = os.path.join(CLEAN, f"version-{version}")
    if not os.path.isdir(ref_dir):
        print(f"v{version}: reference directory missing at {ref_dir}")
        continue

    for name in sorted(os.listdir(ref_dir)):
        if not name.endswith(".pkl"):
            continue
        ref_path = os.path.join(ref_dir, name)
        new_path = os.path.join(clean_dir, name)
        checked += 1

        if not os.path.exists(new_path):
            failures.append((version, name, ["not produced by clean_sources.py"]))
            print(f"  MISSING   v{version}  {name}")
            continue

        problems, worst_ulp = differences(pd.read_pickle(new_path), pd.read_pickle(ref_path))
        if problems:
            failures.append((version, name, problems))
            print(f"  DIFFERS   v{version}  {name}")
            for p in problems[:6]:
                print(f"              {p}")
            if len(problems) > 6:
                print(f"              ... and {len(problems) - 6} more")
        else:
            passed += 1
            note = "exact" if worst_ulp == 0 else f"within {worst_ulp} ULP"
            print(f"  match     v{version}  {name}  ({note})")

print(f"\n{passed} of {checked} tables match the originals "
      f"(floats tolerated to {args.max_ulp} ULP).")
if failures:
    print(f"{len(failures)} table(s) did not match.")
    sys.exit(1)
