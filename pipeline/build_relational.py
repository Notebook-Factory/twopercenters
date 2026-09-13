"""Load every cleaned edition into the relational core and export Parquet.

Load order matters. `load_edition` resolves author identity INCREMENTALLY: the
incoming edition is resolved against the authors already in the database rather
than against one global batch of all editions (RULING R4). That makes adding a
new edition an INSERT instead of a rebuild, but it also means the top-level
build must load editions in ascending data-year order, which `build` does.

Two things about the source files are easy to get wrong:

* Each `data_clean/version-N/` directory holds `<stem>.pkl`,
  `<stem>_LogTransform.pkl` and `<stem>_key.json`. The `_LogTransform` copies
  are log-normalised, so `firstyr` reads as 0.9968 rather than 1971. They are
  excluded here and must never be loaded.
* Version 1 carries two career data years, 2017 and 2018, in separate files,
  and only a 2017 singleyr file. That asymmetry is real, which is why singleyr
  has no 2018 edition.

Dimension values (institution, country, field, subfield) are NFKC-normalised
and then stripped before they are deduplicated (RULING R15). NFKC is needed in
addition to strip because some values carry non-breaking spaces: 'CEA LETI\\xa0'
occurs in versions 2, 3 and 5 and would otherwise become a second institution
beside 'CEA LETI'.
"""
import datetime
import glob
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata

import pandas as pd

from db.connection import connect
from db.migrate import apply_all
from pipeline.column_map import canonical_frame
from pipeline.identity import block_key, normalize, resolve

MANIFEST = "dataset_manifest.json"

# Metric columns that land in the fact tables. Split by the type they are
# written as; the schema's bigint and integer columns are both Python ints.
INT_METRICS = [
    "rank", "h", "np", "nps", "cpsf", "npsfl", "np_cited",
    "rank_ns", "h_ns", "nps_ns", "cpsf_ns", "npsfl_ns", "np_cited_ns",
    "firstyr", "lastyr", "rank_subfield", "rank_subfield_ns", "subfield_count",
    "np_rw", "np_d",
    "nc", "ncs", "ncsf", "ncsfl", "npciting",
    "nc_ns", "ncs_ns", "ncsf_ns", "ncsfl_ns", "npciting_ns",
    "nc_to_rw", "nc_rw", "nc_d",
]
FLOAT_METRICS = ["c", "hm", "cprat", "c_ns", "hm_ns", "cprat_ns", "self_pct"]
METRIC_COLUMNS = INT_METRICS + FLOAT_METRICS

FRACTION_COLUMNS = {
    "field_frac": "sm-field-frac",
    "subfield_1_frac": "sm-subfield-1-frac",
    "subfield_2_frac": "sm-subfield-2-frac",
}

FACT_COLUMNS = [
    "author_id", "edition_id", "institution_id", "field_id", "field_frac",
    "subfield_1_id", "subfield_1_frac", "subfield_2_id", "subfield_2_frac",
    "observation_date",
] + METRIC_COLUMNS

TABLES = [
    "countries", "institutions", "fields", "subfields", "editions", "authors",
    "author_name_observations", "metric_maxima", "career_metrics",
    "singleyr_metrics",
]


# --------------------------------------------------------------------------
# value cleaning
# --------------------------------------------------------------------------

def clean_text(value):
    """NFKC-normalise, then strip. Missing and empty both become None."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return text or None


def _digest(kind, name):
    return hashlib.sha1(f"{kind}|{name}".encode("utf-8")).hexdigest()[:16]


def institution_id(name):
    return _digest("institution", name)


def field_id(name):
    return _digest("field", name)


def subfield_id(name):
    return _digest("subfield", name)


def _int_or_none(value):
    if value is None or value != value:
        return None
    return int(value)


def _float_or_none(value):
    if value is None or value != value:
        return None
    return float(value)


# --------------------------------------------------------------------------
# edition discovery
# --------------------------------------------------------------------------

class EditionFile:
    """One cleaned pickle and the metadata that describes it."""

    def __init__(self, path):
        self.path = path
        stem = os.path.basename(path)[:-4]
        self.key_path = os.path.join(os.path.dirname(path), stem + "_key.json")
        match = re.search(r"(career|singleyr)[-_](\d{4})", stem)
        if match is None:
            raise ValueError(f"cannot read kind and data year from {path}")
        self.kind = match.group(1)
        self.data_year = int(match.group(2))
        self.mendeley_version = int(re.search(r"version-(\d+)", path).group(1))
        self.edition_id = f"{self.kind}-{self.data_year}"
        self.observation_date = datetime.date(self.data_year, 12, 31)

    def key(self):
        with open(self.key_path) as handle:
            return json.load(handle)


def edition_files(path):
    """Every non-LogTransform pickle under `path`, in ascending data year.

    The `_LogTransform` copies are deliberately excluded: they hold
    log-normalised values rather than the source ones.
    """
    found = []
    for candidate in sorted(glob.glob(os.path.join(path, "*.pkl"))):
        if candidate.endswith("_LogTransform.pkl"):
            continue
        found.append(EditionFile(candidate))
    found.sort(key=lambda f: (f.data_year, f.kind))
    return found


def _manifest_entry(source_filename):
    """The publication date and checksum the publishers recorded for a file."""
    if not os.path.exists(MANIFEST):
        return None, None
    with open(MANIFEST) as handle:
        manifest = json.load(handle)
    for version in manifest.get("versions", []):
        for entry in version.get("files", []):
            if entry.get("filename") == source_filename:
                return version.get("publish_date"), entry.get("sha256")
    return None, None


# --------------------------------------------------------------------------
# dimensions
# --------------------------------------------------------------------------

def _copy_rows(conn, statement, rows):
    if not rows:
        return
    with conn.cursor() as cur:
        with cur.copy(statement) as copy:
            for row in rows:
                copy.write_row(row)


def _upsert_dimensions(conn, frame):
    """Insert whatever dimension values this edition introduces.

    An institution is identified by its normalised name alone, so its
    `country_code` is whichever country it was first seen with. 3,389 of the
    66,079 institution names appear with more than one country across the
    editions; the task report records what that costs.
    """
    countries = {}
    institutions = {}
    fields = set()
    subfields = set()

    has_cntry = "cntry" in frame.columns
    if has_cntry:
        for value in frame["cntry"].unique():
            code = clean_text(value)
            if code:
                countries[code] = code
    if "inst_name" in frame.columns:
        cntry_values = frame["cntry"] if has_cntry else [None] * len(frame)
        for raw_inst, raw_cntry in zip(frame["inst_name"], cntry_values):
            name = clean_text(raw_inst)
            if name and name not in institutions:
                institutions[name] = clean_text(raw_cntry)

    if "sm-field" in frame.columns:
        fields = {v for v in (clean_text(x)
                              for x in frame["sm-field"].unique()) if v}
    for column in ("sm-subfield-1", "sm-subfield-2"):
        if column in frame.columns:
            subfields |= {v for v in (clean_text(x)
                                      for x in frame[column].unique()) if v}

    with conn.cursor() as cur:
        cur.executemany(
            "insert into countries (country_code, name) values (%s, %s) "
            "on conflict (country_code) do nothing",
            [(code, name) for code, name in sorted(countries.items())])
        cur.executemany(
            "insert into institutions (institution_id, inst_name, "
            "country_code) values (%s, %s, %s) "
            "on conflict (institution_id) do nothing",
            [(institution_id(name), name, code)
             for name, code in sorted(institutions.items())])
        cur.executemany(
            "insert into fields (field_id, name) values (%s, %s) "
            "on conflict (field_id) do nothing",
            [(field_id(name), name) for name in sorted(fields)])
        cur.executemany(
            "insert into subfields (subfield_id, name) values (%s, %s) "
            "on conflict (subfield_id) do nothing",
            [(subfield_id(name), name) for name in sorted(subfields)])


def _refresh_subfield_parents(conn):
    """Point each subfield at the field it most often appears beside.

    `sm-field` is the author's top-ranked field and `sm-subfield-1` their
    top-ranked subfield, and the two are ranked independently, so one row's
    field is not necessarily the parent of that row's subfield. Across all rows
    the real Science-Metrix parent wins by a wide margin: 'General Chemistry'
    sits beside 'Chemistry' 14,437 times and beside something else 398 times.
    So the modal field is used, with ties broken on field_id to keep the result
    deterministic.
    """
    conn.execute("""
        with pairs as (
            select subfield_1_id as subfield_id, field_id, count(*) as n
            from career_metrics
            where subfield_1_id is not null and field_id is not null
            group by 1, 2
            union all
            select subfield_1_id, field_id, count(*)
            from singleyr_metrics
            where subfield_1_id is not null and field_id is not null
            group by 1, 2
        ), totals as (
            select subfield_id, field_id, sum(n) as n from pairs group by 1, 2
        ), best as (
            select distinct on (subfield_id) subfield_id, field_id
            from totals order by subfield_id, n desc, field_id
        )
        update subfields s set field_id = best.field_id
        from best
        where best.subfield_id = s.subfield_id
          and s.field_id is distinct from best.field_id
    """)


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def _firstyr_values(frame):
    if "firstyr" not in frame.columns:
        return [None] * len(frame)
    numeric = pd.to_numeric(frame["firstyr"], errors="coerce")
    return [_int_or_none(v) for v in numeric.tolist()]


def _new_observations(frame, edition_id):
    authfull = frame["authfull"].tolist()
    firstyr = _firstyr_values(frame)
    inst = (frame["inst_name"].tolist() if "inst_name" in frame.columns
            else [None] * len(authfull))
    cntry = (frame["cntry"].tolist() if "cntry" in frame.columns
             else [None] * len(authfull))
    return [
        {"edition_id": edition_id, "authfull": a, "firstyr": y,
         "inst_name": i, "cntry": c}
        for a, y, i, c in zip(authfull, firstyr, inst, cntry)
    ]


def _relevant_prior_observations(conn, observations):
    """The already-loaded observations this edition can actually change.

    Each (surname, first initial, firstyr) group is resolved independently of
    every other group, and within a group the outcome turns on a single
    question: does any one edition contribute two or more rows? So a prior
    group's rows only need to go back through `resolve` when

      * the group is already ambiguous, in which case the incoming rows must
        inherit that ambiguity instead of being handed the confident id, or
      * the incoming edition has two or more rows in the group, which flips a
        previously confident group and reassigns the rows already stored for
        it.

    Every other prior group would resolve to exactly what is already stored, so
    it is left out. That is what keeps an incremental load cheap rather than
    re-resolving 2.7 million observations for each new edition.
    """
    prior = []
    seen = set()

    def collect(rows):
        for _surname, _initial, firstyr, edition_id, authfull, author_id in rows:
            marker = (edition_id, author_id, authfull)
            if marker in seen:
                continue
            seen.add(marker)
            prior.append({
                "edition_id": edition_id, "authfull": authfull,
                "firstyr": firstyr, "inst_name": None, "cntry": None,
                "_author_id": author_id,
            })

    select = ("select a.surname, a.first_initial, a.firstyr, o.edition_id, "
              "o.authfull_raw, o.author_id "
              "from author_name_observations o "
              "join authors a using (author_id) ")

    collect(conn.execute(select + "where a.is_ambiguous").fetchall())

    counts = {}
    for obs in observations:
        surname, initial = block_key(obs["authfull"])
        key = (surname, initial, obs["firstyr"])
        counts[key] = counts.get(key, 0) + 1
    repeated = [key for key, n in counts.items() if n > 1]
    if repeated:
        rows = conn.execute(
            select + "where (a.surname, a.first_initial) in "
                     "(select * from unnest(%s::text[], %s::text[]))",
            ([k[0] for k in repeated], [k[1] for k in repeated])).fetchall()
        wanted = set(repeated)
        collect([r for r in rows if (r[0], r[1], r[2]) in wanted])

    return prior


def _resolve_by_firstyr(observations):
    """Resolve one firstyr at a time, grouped by (edition_id, authfull).

    `resolve` blocks on surname and first initial, then splits each block by
    firstyr and treats every firstyr group independently, so resolving one
    firstyr at a time gives exactly the same answer as resolving everything at
    once. Doing it that way is what makes (edition_id, authfull) enough to pair
    a Resolution back to the row it came from: Resolution does not carry
    firstyr, so without the split two rows sharing a name but not a firstyr
    would be indistinguishable.
    """
    partitions = {}
    for obs in observations:
        partitions.setdefault(obs["firstyr"], []).append(obs)

    for firstyr, partition in partitions.items():
        grouped = {}
        for resolution in resolve(partition):
            grouped.setdefault(
                (resolution.edition_id, resolution.authfull),
                []).append(resolution)
        yield firstyr, grouped


def _pair(rows, resolutions):
    """Pair one edition's rows for one name with that name's resolutions.

    For an ambiguous group `resolve` orders the edition's rows by normalised
    institution, then country, then name, and hands out one id per position.
    Restricting that order to a single name leaves the rows ordered by
    institution then country, so sorting the same way here reproduces the
    assignment `resolve` intended.
    """
    if len(rows) == 1:
        return [(rows[0], resolutions[0])]
    ordered = sorted(rows, key=lambda r: (
        normalize(r[1].get("inst_name") or ""),
        normalize(r[1].get("cntry") or "")))
    return list(zip(ordered, resolutions))


def _resolve_edition(conn, observations):
    """Give every row of the incoming edition an author.

    Returns (assignments, remaps). `assignments` holds one Resolution per
    incoming row, in row order. `remaps` maps (old author_id, edition_id) to a
    new author_id for rows of earlier editions whose group has just become
    ambiguous, which is the only way an already-stored id can change.
    """
    edition_id = observations[0]["edition_id"]
    prior = _relevant_prior_observations(conn, observations)

    assignments = [None] * len(observations)
    remaps = {}

    incoming = {}
    for index, obs in enumerate(observations):
        incoming.setdefault(
            (obs["firstyr"], obs["authfull"]), []).append((index, obs))

    # Old and new ids are compared per whole block, not per name. An already
    # ambiguous block hands out the same set of ids either way, but not
    # necessarily the same id to the same name: the ordinals are decided by
    # institution and country, which prior observations no longer carry. At
    # block level that reshuffling cancels out and only a real change shows.
    stored_ids = {}
    for obs in prior:
        surname, initial = block_key(obs["authfull"])
        stored_ids.setdefault(
            (surname, initial, obs["firstyr"], obs["edition_id"]),
            set()).add(obs["_author_id"])
    resolved_ids = {}

    for firstyr, grouped in _resolve_by_firstyr(prior + observations):
        for (resolved_edition, authfull), resolutions in grouped.items():
            if resolved_edition == edition_id:
                rows = incoming[(firstyr, authfull)]
                for (index, _obs), resolution in _pair(rows, resolutions):
                    assignments[index] = resolution
                continue
            surname, initial = block_key(authfull)
            resolved_ids.setdefault(
                (surname, initial, firstyr, resolved_edition),
                set()).update(r.author_id for r in resolutions)

    for block, old_ids in stored_ids.items():
        new_ids = resolved_ids.get(block, set())
        if old_ids == new_ids:
            continue
        # Ambiguity only ever spreads, so the ids can differ in one way only:
        # a confident block has just flipped. A confident block holds at most
        # one row per edition, which makes this a one-for-one swap.
        if len(old_ids) != 1 or len(new_ids) != 1:
            raise RuntimeError(
                f"block {block} changed from {sorted(old_ids)} to "
                f"{sorted(new_ids)}, which is not a confident-to-ambiguous "
                "flip")
        remaps[(old_ids.pop(), block[3])] = new_ids.pop()

    unassigned = [i for i, a in enumerate(assignments) if a is None]
    if unassigned:
        raise RuntimeError(
            f"{len(unassigned)} rows of {edition_id} were not assigned an "
            f"author; the first is {observations[unassigned[0]]}")
    return assignments, remaps


def _apply_remaps(conn, remaps):
    """Move earlier editions' rows onto the ids their group now resolves to."""
    if not remaps:
        return 0
    with conn.cursor() as cur:
        for (old, edition_id), new in sorted(remaps.items()):
            cur.execute("""
                insert into authors (author_id, authfull_display,
                    name_normalized, surname, first_initial, firstyr,
                    is_ambiguous, first_data_year, last_data_year)
                select %s, authfull_display, name_normalized, surname,
                       first_initial, firstyr, true,
                       (select data_year from editions where edition_id = %s),
                       (select data_year from editions where edition_id = %s)
                from authors where author_id = %s
                on conflict (author_id) do nothing
            """, (new, edition_id, edition_id, old))
            for table in ("author_name_observations", "career_metrics",
                          "singleyr_metrics"):
                cur.execute(
                    f"update {table} set author_id = %s "
                    "where author_id = %s and edition_id = %s",
                    (new, old, edition_id))
        cur.execute("""
            delete from authors a
            where a.author_id = any(%s)
              and not exists (select 1 from author_name_observations o
                              where o.author_id = a.author_id)
        """, ([old for old, _edition in remaps],))
    return len(remaps)


def _write_authors(conn, frame, edition, assignments):
    """Insert or refresh one author row, and one name observation, per row."""
    authfull = frame["authfull"].tolist()
    firstyr = _firstyr_values(frame)

    author_rows = []
    observation_rows = []
    for raw_name, year, resolution in zip(authfull, firstyr, assignments):
        surname, initial = block_key(raw_name)
        author_rows.append((
            resolution.author_id, str(raw_name), normalize(raw_name), surname,
            initial, year, not resolution.is_confident, edition.data_year))
        observation_rows.append((
            resolution.author_id, edition.edition_id, str(raw_name),
            resolution.method, resolution.is_confident))

    conn.execute("""
        create temp table tmp_authors (
            author_id text, authfull_display text, name_normalized text,
            surname text, first_initial text, firstyr integer,
            is_ambiguous boolean, data_year integer)
    """)
    _copy_rows(conn, "copy tmp_authors from stdin", author_rows)
    conn.execute("""
        insert into authors (author_id, authfull_display, name_normalized,
            surname, first_initial, firstyr, is_ambiguous, first_data_year,
            last_data_year)
        select author_id, authfull_display, name_normalized, surname,
               first_initial, firstyr, is_ambiguous, data_year, data_year
        from tmp_authors
        on conflict (author_id) do update set
            authfull_display = excluded.authfull_display,
            is_ambiguous = authors.is_ambiguous or excluded.is_ambiguous,
            first_data_year = least(authors.first_data_year,
                                    excluded.first_data_year),
            last_data_year = greatest(authors.last_data_year,
                                      excluded.last_data_year)
    """)
    conn.execute("drop table tmp_authors")

    conn.execute("""
        create temp table tmp_observations (
            author_id text, edition_id text, authfull_raw text,
            resolution_method text, is_confident boolean)
    """)
    _copy_rows(conn, "copy tmp_observations from stdin", observation_rows)
    conn.execute("""
        insert into author_name_observations (author_id, edition_id,
            authfull_raw, resolution_method, is_confident)
        select author_id, edition_id, authfull_raw, resolution_method,
               is_confident
        from tmp_observations
        on conflict (edition_id, authfull_raw, author_id) do nothing
    """)
    conn.execute("drop table tmp_observations")


def _refresh_collision_group_size(conn, edition_id):
    """Count the distinct authors sharing each (surname, initial, firstyr)."""
    conn.execute("""
        with touched as (
            select distinct a.surname, a.first_initial, a.firstyr
            from authors a join author_name_observations o using (author_id)
            where o.edition_id = %s
        ), sizes as (
            select a.surname, a.first_initial, a.firstyr, count(*) as n
            from authors a
            join touched t on t.surname = a.surname
                          and t.first_initial = a.first_initial
                          and t.firstyr is not distinct from a.firstyr
            group by 1, 2, 3
        )
        update authors a set collision_group_size = sizes.n
        from sizes
        where sizes.surname = a.surname
          and sizes.first_initial = a.first_initial
          and sizes.firstyr is not distinct from a.firstyr
          and a.collision_group_size is distinct from sizes.n
    """, (edition_id,))


# --------------------------------------------------------------------------
# facts
# --------------------------------------------------------------------------

def _numeric_column(frame, name, converter):
    if name not in frame.columns:
        return None
    numeric = pd.to_numeric(frame[name], errors="coerce")
    return [converter(v) for v in numeric.tolist()]


def _write_facts(conn, frame, edition, assignments):
    length = len(frame)
    blank = [None] * length
    table = f"{edition.kind}_metrics"

    def dimension(column, id_for):
        if column not in frame.columns:
            return blank
        values = []
        for raw in frame[column]:
            name = clean_text(raw)
            values.append(None if name is None else id_for(name))
        return values

    columns = {
        "author_id": [a.author_id for a in assignments],
        "edition_id": [edition.edition_id] * length,
        "institution_id": dimension("inst_name", institution_id),
        "field_id": dimension("sm-field", field_id),
        "subfield_1_id": dimension("sm-subfield-1", subfield_id),
        "subfield_2_id": dimension("sm-subfield-2", subfield_id),
        "observation_date": [edition.observation_date] * length,
    }
    for target, source in FRACTION_COLUMNS.items():
        columns[target] = _numeric_column(frame, source, _float_or_none) or blank
    for name in INT_METRICS:
        columns[name] = _numeric_column(frame, name, _int_or_none) or blank
    for name in FLOAT_METRICS:
        columns[name] = _numeric_column(frame, name, _float_or_none) or blank

    statement = f"copy {table} ({', '.join(FACT_COLUMNS)}) from stdin"
    with conn.cursor() as cur:
        with cur.copy(statement) as copy:
            for row in zip(*(columns[name] for name in FACT_COLUMNS)):
                copy.write_row(row)
    return length


def _write_maxima(conn, frame, edition):
    """Record every metric's maximum for this edition.

    The dashboard renders log(x + 1) / log(max + 1) at request time instead of
    storing a log-transformed copy of the data, so it needs the maximum the
    edition's own data reached.
    """
    rows = []
    for name in METRIC_COLUMNS:
        if name not in frame.columns:
            continue
        value = pd.to_numeric(frame[name], errors="coerce").max()
        if value is None or value != value:
            continue
        rows.append((edition.edition_id, name, float(value)))
    with conn.cursor() as cur:
        cur.executemany(
            "insert into metric_maxima (edition_id, metric, max_value) "
            "values (%s, %s, %s) "
            "on conflict (edition_id, metric) do update set "
            "max_value = excluded.max_value", rows)


# --------------------------------------------------------------------------
# per-file load
# --------------------------------------------------------------------------

def _load_file(conn, edition):
    frame = canonical_frame(pd.read_pickle(edition.path))
    source_filename = edition.key().get("source")
    published_date, sha256 = _manifest_entry(source_filename)

    # RULING R7: column_map deliberately drops 2017's name2/frac2, so version 1
    # has no second subfield. Recording what each edition actually carried
    # makes that omission data rather than silence.
    columns_present = sorted(str(column) for column in frame.columns)

    conn.execute("""
        insert into editions (edition_id, mendeley_version, data_year, kind,
            observation_date, published_date, source_filename, sha256,
            columns_present)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (edition_id) do update set
            mendeley_version = excluded.mendeley_version,
            observation_date = excluded.observation_date,
            published_date = excluded.published_date,
            source_filename = excluded.source_filename,
            sha256 = excluded.sha256,
            columns_present = excluded.columns_present
    """, (edition.edition_id, edition.mendeley_version, edition.data_year,
          edition.kind, edition.observation_date, published_date,
          source_filename, sha256, json.dumps(columns_present)))

    _upsert_dimensions(conn, frame)

    observations = _new_observations(frame, edition.edition_id)
    assignments, remaps = _resolve_edition(conn, observations)
    _apply_remaps(conn, remaps)
    _write_authors(conn, frame, edition, assignments)

    rows = _write_facts(conn, frame, edition, assignments)
    _write_maxima(conn, frame, edition)
    _refresh_subfield_parents(conn)
    _refresh_collision_group_size(conn, edition.edition_id)
    conn.commit()
    return rows


def load_edition(conn, path, kind):
    """Load every `kind` edition under `path` and return the rows loaded.

    Identity is resolved incrementally, against the authors already in the
    database plus the incoming edition, so LOAD ORDER MATTERS: editions must be
    loaded in ascending data-year order, which is what `build` does. Within
    `path` the files are ordered by data year too, which is why version 1's
    2017 career edition is loaded before its 2018 one.
    """
    total = 0
    for edition in edition_files(path):
        if edition.kind != kind:
            continue
        total += _load_file(conn, edition)
    return total


# --------------------------------------------------------------------------
# parquet export
# --------------------------------------------------------------------------

def export_parquet(conn, out_dir="data_parquet"):
    """Write one `<table>.parquet` per table into `out_dir`."""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for table in TABLES:
        buffer = io.BytesIO()
        with conn.cursor() as cur:
            statement = f"copy {table} to stdout (format csv, header true)"
            with cur.copy(statement) as copy:
                for chunk in copy:
                    buffer.write(bytes(chunk))
        buffer.seek(0)
        frame = pd.read_csv(buffer, low_memory=False)
        target = os.path.join(out_dir, f"{table}.parquet")
        frame.to_parquet(target, index=False)
        written.append((target, len(frame)))
    return written


# --------------------------------------------------------------------------
# top level
# --------------------------------------------------------------------------

def build(conn, root="data_clean", out_dir="data_parquet"):
    """Load every edition under `root` in ascending data-year order.

    The order is required rather than cosmetic: identity resolution is
    incremental (RULING R4), so each edition is resolved against whatever is
    already loaded.
    """
    editions = []
    for directory in sorted(glob.glob(os.path.join(root, "version-*"))):
        editions.extend(edition_files(directory))
    editions.sort(key=lambda f: (f.data_year, f.kind))

    counts = []
    for edition in editions:
        started = time.time()
        rows = _load_file(conn, edition)
        counts.append((edition.edition_id, rows))
        print(f"{edition.edition_id:>16}  {rows:>9,} rows  "
              f"{time.time() - started:7.1f}s", flush=True)
    for target, rows in export_parquet(conn, out_dir):
        print(f"wrote {target} ({rows:,} rows)", flush=True)
    return counts


def main(argv):
    root = argv[1] if len(argv) > 1 else "data_clean"
    started = time.time()
    with connect() as conn:
        apply_all(conn, "db/migrations")
        counts = build(conn, root)
    total = sum(rows for _edition, rows in counts)
    print(f"total {total:,} rows in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main(sys.argv)
