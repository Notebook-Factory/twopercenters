"""Map each edition's year-stamped column names onto stable canonical names.

Every edition renames the same quantities: np6017 in 2017 is np6024 in 2024.
This is the sole reason standardize_col_names existed. Here the year is stripped
and lives in the row instead, via edition_id.
"""
import re

# Checked in order. The first match wins, so longer patterns come first.
PATTERNS = [
    (re.compile(r"^np\d{4} cited\d{4}$"), "np_cited"),
    (re.compile(r"^nc\d{4}_to_rw$"), "nc_to_rw"),
    (re.compile(r"^nc\d{4}_rw$"), "nc_rw"),
    (re.compile(r"^np\d{4}_rw$"), "np_rw"),
    (re.compile(r"^nc\d{4}_d$"), "nc_d"),
    (re.compile(r"^np\d{4}_d$"), "np_d"),
    (re.compile(r"^np\d{4}$"), "np"),
    (re.compile(r"^nc\d{4}$"), "nc"),
    (re.compile(r"^hm\d{2}$"), "hm"),
    (re.compile(r"^h\d{2}$"), "h"),
]

LITERAL = {
    "self%": "self_pct",
    "rank sm-subfield-1": "rank_subfield",
    "sm-subfield-1 count": "subfield_count",
    # Renamed after the 2017 edition; both mean single+first authored papers.
    "npsf": "cpsf",
    # The 2017 edition's taxonomy, mapped onto every later edition's scheme.
    # name1/frac1 is the 176-subfield level, name22/frac22 the 22-field level;
    # Table-S3.xlsx sheets SM176 and SM22 are the code-to-name lookups.
    "name1": "sm-subfield-1",
    "frac1": "sm-subfield-1-frac",
    "name22": "sm-field",
    "frac22": "sm-field-frac",
}

# Present in the source but deliberately not loaded: 2017's numeric taxonomy
# codes, which have no equivalent in any later edition.
DROP = {"sm-1", "sm-2", "sm22", "name2", "frac2"}

PASS_THROUGH = {
    "authfull", "inst_name", "cntry", "firstyr", "lastyr", "rank", "c",
    "nps", "ncs", "cpsf", "ncsf", "npsfl", "ncsfl", "npciting", "cprat",
    "sm-subfield-1", "sm-subfield-1-frac", "sm-subfield-2",
    "sm-subfield-2-frac", "sm-field", "sm-field-frac",
}


def canonical(raw_name):
    name = str(raw_name).strip()

    suffix = ""
    if name.endswith(" (ns)"):
        name, suffix = name[:-5].strip(), "_ns"

    if name in DROP:
        return None
    if name in LITERAL:
        return LITERAL[name] + suffix
    if name in PASS_THROUGH:
        return name + suffix
    for pattern, replacement in PATTERNS:
        if pattern.match(name):
            return replacement + suffix
    return None


def canonical_frame(df):
    renames, drops = {}, []
    for column in df.columns:
        mapped = canonical(column)
        if mapped is None:
            drops.append(column)
        else:
            renames[column] = mapped
    return df.drop(columns=drops).rename(columns=renames)
