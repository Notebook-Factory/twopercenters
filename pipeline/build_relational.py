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
from pipeline.ror_match import refresh_institution_ror

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
    "author_id", "edition_id", "institution_id", "country_code", "field_id",
    "field_frac", "subfield_1_id", "subfield_1_frac", "subfield_2_id",
    "subfield_2_frac", "observation_date",
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
    editions.
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


def _column_or_nones(frame, column, length):
    return (frame[column].tolist() if column in frame.columns
            else [None] * length)


def _new_observations(frame, edition_id):
    authfull = frame["authfull"].tolist()
    firstyr = _firstyr_values(frame)
    inst = _column_or_nones(frame, "inst_name", len(authfull))
    cntry = _column_or_nones(frame, "cntry", len(authfull))
    # The matching signals. identity.resolve only reads these inside an
    # ambiguous block, where the name has already failed to separate people
    # and the career has to. The composite score c does most of the work: it
    # moves by a median of 0.42% a year for a real person.
    score = _column_or_nones(frame, "c", len(authfull))
    h_index = _column_or_nones(frame, "h", len(authfull))
    field = _column_or_nones(frame, "sm-field", len(authfull))
    subfield = _column_or_nones(frame, "sm-subfield-1", len(authfull))
    return [
        {"edition_id": edition_id, "authfull": a, "firstyr": y,
         "inst_name": i, "cntry": c, "c": s, "h": hh,
         "field": f, "subfield": sf}
        for a, y, i, c, s, hh, f, sf in zip(
            authfull, firstyr, inst, cntry, score, h_index, field, subfield)
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
        for (_surname, _initial, firstyr, edition_id, authfull, author_id,
             score, h_index, inst_name, cntry, field, subfield) in rows:
            marker = (edition_id, author_id, authfull)
            if marker in seen:
                continue
            seen.add(marker)
            prior.append({
                "edition_id": edition_id, "authfull": authfull,
                "firstyr": firstyr, "inst_name": inst_name, "cntry": cntry,
                "c": score, "h": h_index, "field": field,
                "subfield": subfield,
                "_author_id": author_id,
            })

    # The matching signals have to come back in the same form the incoming
    # edition supplies them: names, not the hashed ids the fact tables store,
    # or a prior observation could never compare equal to a new one. Country
    # is the exception and needs no join, because the raw `cntry` value IS
    # the country_code.
    select = (
        "with metrics as ("
        "  select author_id, edition_id, c, h, institution_id, country_code,"
        "         field_id, subfield_1_id from career_metrics"
        "  union all"
        "  select author_id, edition_id, c, h, institution_id, country_code,"
        "         field_id, subfield_1_id from singleyr_metrics"
        ") "
        "select a.surname, a.first_initial, a.firstyr, o.edition_id, "
        "o.authfull_raw, o.author_id, "
        "m.c, m.h, i.inst_name, m.country_code, f.name, sf.name "
        "from author_name_observations o "
        "join authors a using (author_id) "
        "left join metrics m on m.author_id = o.author_id "
        "  and m.edition_id = o.edition_id "
        "left join institutions i on i.institution_id = m.institution_id "
        "left join fields f on f.field_id = m.field_id "
        "left join subfields sf on sf.subfield_id = m.subfield_1_id ")

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
    """Resolve one firstyr at a time.

    `resolve` blocks on surname and first initial, then splits each block by
    firstyr and treats every firstyr group independently, so resolving one
    firstyr at a time gives exactly the same answer as resolving everything
    at once, and gives the caller the firstyr each Resolution belongs to,
    which Resolution itself does not carry.
    """
    partitions = {}
    for obs in observations:
        partitions.setdefault(obs["firstyr"], []).append(obs)

    for firstyr, partition in partitions.items():
        yield firstyr, resolve(partition)


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

    # Every observation is tagged so a Resolution can be traced back to the
    # exact row it came from. Inside an ambiguous block several rows share an
    # edition and a name, so that pair does not identify a row, and an
    # earlier version paired them by sorting both sides the same way. That
    # worked only while ambiguous ids were handed out in a known order; now
    # they follow a chain built from the career, and position means nothing.
    for index, obs in enumerate(observations):
        obs["_token"] = ("incoming", index)
    for index, obs in enumerate(prior):
        obs["_token"] = ("prior", index)

    # An already-stored row moves to a new author whenever re-resolving its
    # block puts it on a different chain. Comparing per observation rather
    # than per block is what makes that expressible: the resolution carries
    # the token of the exact row it came from, so the old id and the new one
    # are known for that row rather than inferred from two sets.
    #
    # An earlier version compared id sets per block and raised unless the
    # difference was a confident-to-ambiguous flip. That held while ambiguous
    # ids were minted per edition and could only ever be reshuffled within
    # one. Chain ids are derived from the career now, so a later edition can
    # legitimately change an earlier row's author: career-2020's
    # `Johnson, Mary Ann` continues the dormant usa `Johnson, Mark` chain at
    # a cost of about 4.4, under the threshold, and whether she does depends
    # on what else the block holds when it is re-resolved. That is the
    # matcher working, not a corruption, and the remap machinery already
    # knows how to move rows.
    for firstyr, resolutions in _resolve_by_firstyr(prior + observations):
        for resolution in resolutions:
            source, index = resolution.token
            if source == "incoming":
                assignments[index] = resolution
                continue
            stored = prior[index]["_author_id"]
            if resolution.author_id != stored:
                remaps[(stored, resolution.edition_id)] = resolution.author_id

    unassigned = [i for i, a in enumerate(assignments) if a is None]
    if unassigned:
        raise RuntimeError(
            f"{len(unassigned)} rows of {edition_id} were not assigned an "
            f"author; the first is {observations[unassigned[0]]}")
    return assignments, remaps


def _apply_remaps(conn, remaps):
    """Move earlier editions' rows onto the ids their group now resolves to.

    Via a temporary id, because a block's ids can be permuted rather than
    merely reassigned. Two chains indistinguishable on every attribute can
    exchange ordinals, making the remap a swap: A to B and B to A. Applied
    one at a time, the first update lands on an id the second has not vacated
    yet and `author_name_observations_edition_id_authfull_raw_author_id_key`
    rejects it. Observed on `Zhang, Lei` in singleyr-2017.

    This does not weaken that constraint. A genuine merge, two rows of one
    edition ending up on one author, still collides when the parked rows are
    unparked, which is what should happen.

    `authors` has a foreign key from every fact table, so the parking id has
    to exist as an author row before anything points at it, and has to be
    removed once nothing does.
    """
    if not remaps:
        return 0

    parking = {
        (old, edition_id):
            "tmp-" + hashlib.sha1(
                f"{old}|{edition_id}".encode("utf-8")).hexdigest()[:12]
        for (old, edition_id) in remaps
    }
    tables = ("author_name_observations", "career_metrics",
              "singleyr_metrics")

    with conn.cursor() as cur:
        for (old, edition_id), parked in sorted(parking.items()):
            cur.execute("""
                insert into authors (author_id, authfull_display,
                    name_normalized, surname, first_initial, firstyr,
                    is_ambiguous, first_data_year, last_data_year)
                select %s, authfull_display, name_normalized, surname,
                       first_initial, firstyr, true,
                       first_data_year, last_data_year
                from authors where author_id = %s
                on conflict (author_id) do nothing
            """, (parked, old))
            for table in tables:
                cur.execute(
                    f"update {table} set author_id = %s "
                    "where author_id = %s and edition_id = %s",
                    (parked, old, edition_id))

        for (old, edition_id), new in sorted(remaps.items()):
            parked = parking[(old, edition_id)]
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
            """, (new, edition_id, edition_id, parked))
            for table in tables:
                cur.execute(
                    f"update {table} set author_id = %s "
                    "where author_id = %s and edition_id = %s",
                    (new, parked, edition_id))

        # Anything left holding no observations goes: the parking rows always,
        # and any old author every one of whose rows moved away.
        cur.execute("""
            delete from authors a
            where a.author_id = any(%s)
              and not exists (select 1 from author_name_observations o
                              where o.author_id = a.author_id)
        """, (list(parking.values()) + [old for old, _e in remaps],))
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
        # RULING R17: the row's own country, not its institution's. Measured
        # on the loaded data, after NFKC and strip: 39,476 rows have an
        # institution whose country is not the row's own, and a further 695
        # have a country but no institution at all. So reading country back
        # through institutions would serve 40,171 rows (1.47%) a country that
        # is not theirs or none at all.
        "country_code": dimension("cntry", lambda code: code),
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

def _check_load_order(conn, edition):
    """Refuse an edition older than one already loaded for the same kind.

    RULING R4 makes identity resolution incremental, so an edition is resolved
    against what is already in the database. Loading 2017 after 2024 therefore
    produces different author ids than a real build does, silently. The
    invariant was documented before it was enforced, which is a trap for
    whoever adds version 9 next September; this is the enforcement.

    The check is per kind because identity resolution runs within one kind
    (see pipeline/matching.py), so the order between kinds does not affect
    the ids it assigns.
    """
    latest = conn.execute(
        "select max(data_year) from editions where kind = %s",
        (edition.kind,)).fetchone()[0]
    if latest is not None and edition.data_year < latest:
        raise ValueError(
            f"{edition.edition_id} would be loaded after {edition.kind} "
            f"{latest}, but identity resolution is incremental (RULING R4) and "
            "requires ascending data-year order within a kind. Load editions "
            "oldest first, as build() does, or rebuild from an empty schema.")


# Known gap: singleyr-2017 carries no firstyr, and firstyr is part of the
# blocking key, so none of its 106,368 rows can join the same person's career
# record (John Ioannidis is two authors for this reason). Borrowing firstyr
# from the career file recovers 68,890 rows, but doing it after editions are
# loaded moves rows between blocks, and _relevant_prior_observations assumes
# every author in a block shares the is_ambiguous flag. Fixing it means
# backfilling before any edition is loaded, or making that fetch complete for
# a block regardless of the flag.


def _load_file(conn, edition):
    _check_load_order(conn, edition)
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

    The order is enforced, not merely documented: `_check_load_order` raises if
    the incoming edition is older than one already loaded for the same kind.
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

# Postgres type -> the pandas dtype the Parquet file should carry. Everything
# not listed here (text, jsonb) becomes pandas "string".
PARQUET_DTYPES = {
    "boolean": "boolean",
    "smallint": "Int64",
    "integer": "Int64",
    "bigint": "Int64",
    "real": "float64",
    "double precision": "float64",
    "numeric": "float64",
}

# COPY writes an unquoted empty field for NULL and a quoted "" for a genuine
# empty string, a distinction read_csv cannot make. Asking COPY for an explicit
# NULL marker removes the ambiguity.
NULL_MARKER = "\\N"


def _column_types(conn, table):
    return dict(conn.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema = 'public' and table_name = %s "
        "order by ordinal_position", (table,)).fetchall())


def export_parquet(conn, out_dir="data_parquet"):
    """Write one `<table>.parquet` per table into `out_dir`, keeping types.

    The types matter: these files are the input to a follow-on project that
    builds a relational graph from them. Left to infer from CSV, pandas reads
    Postgres booleans back as the strings 't' and 'f', and turns text columns
    that happen to look numeric into numbers. So every column is cast to the
    dtype its Postgres type calls for, using nullable extension dtypes
    (Int64, boolean, string) because most of these columns are nullable.
    """
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for table in TABLES:
        types = _column_types(conn, table)
        buffer = io.BytesIO()
        with conn.cursor() as cur:
            statement = (f"copy {table} to stdout "
                         f"(format csv, header true, null '{NULL_MARKER}')")
            with cur.copy(statement) as copy:
                for chunk in copy:
                    buffer.write(bytes(chunk))
        buffer.seek(0)
        frame = pd.read_csv(buffer, dtype=str, keep_default_na=False,
                            na_values=[NULL_MARKER], low_memory=False)

        for column in frame.columns:
            postgres_type = types.get(column, "text")
            dtype = PARQUET_DTYPES.get(postgres_type)
            if postgres_type == "boolean":
                frame[column] = frame[column].map(
                    {"t": True, "f": False}).astype("boolean")
            elif postgres_type == "date":
                frame[column] = pd.to_datetime(frame[column]).dt.date
            elif dtype is not None:
                frame[column] = pd.to_numeric(
                    frame[column], errors="coerce").astype(dtype)
            else:
                frame[column] = frame[column].astype("string")

        target = os.path.join(out_dir, f"{table}.parquet")
        frame.to_parquet(target, index=False)
        written.append((target, len(frame)))
    return written


# --------------------------------------------------------------------------
# top level
# --------------------------------------------------------------------------

def refresh_group_metrics(conn):
    """Refresh the group_metrics materialized view (RULING R24).

    A materialized view does not update itself as its underlying tables
    change, and `pg_matviews.ispopulated` stays true even when the view holds
    zero rows -- it only tracks whether a refresh has ever completed, not
    whether the data is current. So this is a required, not optional, step of
    a full build: skipping it leaves group_metrics silently stale.

    Migrations may run in an order where group_metrics has not been created
    yet, so this is a guarded no-op rather than an error in that case.
    """
    exists = conn.execute(
        "select 1 from pg_matviews where schemaname = 'public' "
        "and matviewname = 'group_metrics'"
    ).fetchone()
    if not exists:
        print("group_metrics does not exist yet; skipping refresh", flush=True)
        return
    started = time.time()
    conn.execute("refresh materialized view group_metrics")
    conn.commit()
    print(f"refreshed group_metrics in {time.time() - started:.1f}s", flush=True)


# The seven questions the Top 10 tab asks, in the order it draws them.
TOP_METRICS = ("c", "nc", "h", "hm", "ncs", "ncsf", "ncsfl")
TOP_N = 10
_METRIC_TABLE_BY_KIND = {"career": "career_metrics",
                         "singleyr": "singleyr_metrics"}


def refresh_top_researchers(conn):
    """Fill top_researchers from the fact tables (migration 012).

    Seven metrics in two column sets over fifteen editions is 210 ordering
    queries, which together take about seven seconds. Each one is the query
    the dashboard would otherwise run on a picker change, and the slowest of
    them takes 640 ms against a cold cache.

    Like refresh_group_metrics, this is a guarded no-op when the table does
    not exist, so a database that has not applied 012 can still finish a
    build.
    """
    exists = conn.execute(
        "select 1 from information_schema.tables "
        "where table_schema = 'public' and table_name = 'top_researchers'"
    ).fetchone()
    if not exists:
        print("top_researchers does not exist yet; skipping refresh",
              flush=True)
        return

    started = time.time()
    editions = conn.execute(
        "select edition_id, kind from editions where superseded_by is null "
        "order by edition_id").fetchall()
    conn.execute("truncate top_researchers")
    written = 0
    for edition_id, kind in editions:
        table = _METRIC_TABLE_BY_KIND.get(kind)
        if table is None:
            continue
        for metric in TOP_METRICS:
            for ns in (False, True):
                suffix = "_ns" if ns else ""
                rows = conn.execute(
                    f"select author_id, {metric}{suffix} from {table} "
                    f"where edition_id = %s and {metric}{suffix} is not null "
                    f"order by {metric}{suffix} desc, author_id limit %s",
                    (edition_id, TOP_N)).fetchall()
                with conn.cursor() as cur:
                    cur.executemany(
                        "insert into top_researchers (kind, edition_id, "
                        "metric, ns, position, author_id, value) "
                        "values (%s, %s, %s, %s, %s, %s, %s)",
                        [(kind, edition_id, metric, ns, position, author_id,
                          float(value))
                         for position, (author_id, value)
                         in enumerate(rows, start=1)])
                written += len(rows)
    conn.commit()
    print(f"filled top_researchers with {written:,} rows in "
          f"{time.time() - started:.1f}s", flush=True)


def refresh_dropdown_views(conn):
    """Refresh dropdown_options and dropdown_stats (migration 007).

    Same contract as refresh_group_metrics and for the same reason: a
    materialized view does not follow its underlying tables, so leaving these
    unrefreshed after a load means the Compare and Author-vs-group tabs offer
    the previous build's option lists. Guarded per view, because a database
    that has not applied migration 007 yet should not fail the build.
    """
    for name in ("dropdown_options", "dropdown_stats"):
        exists = conn.execute(
            "select 1 from pg_matviews where schemaname = 'public' "
            "and matviewname = %s", (name,)
        ).fetchone()
        if not exists:
            print(f"{name} does not exist yet; skipping refresh", flush=True)
            continue
        started = time.time()
        conn.execute(f"refresh materialized view {name}")
        conn.commit()
        print(f"refreshed {name} in {time.time() - started:.1f}s", flush=True)


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

    # RULING R24, applied to the first command anyone runs on a fresh host.
    # Without this, a missing or empty data_clean/ made the whole build a
    # no-op that still exited 0: no editions loaded, empty Parquet written,
    # group_metrics and the dropdown views refreshed down to zero rows, and
    # "total 0 rows" printed. That is a silent empty build, and it is most
    # likely to happen exactly where it does the most damage, since
    # data_clean/ is gitignored and so is absent from a fresh git push.
    if not editions:
        raise SystemExit(
            f"no editions found under {root!r}: expected one or more "
            f"{os.path.join(root, 'version-N')} directories containing "
            "<stem>.pkl files. Nothing was loaded and nothing was "
            "refreshed. If this is a fresh deployment, the data has to get "
            "onto the host first: see the 'Getting the data onto the host' "
            "section of README.md."
        )

    counts = []
    for edition in editions:
        started = time.time()
        rows = _load_file(conn, edition)
        counts.append((edition.edition_id, rows))
        print(f"{edition.edition_id:>16}  {rows:>9,} rows  "
              f"{time.time() - started:7.1f}s", flush=True)
    for target, rows in export_parquet(conn, out_dir):
        print(f"wrote {target} ({rows:,} rows)", flush=True)
    refresh_group_metrics(conn)
    refresh_dropdown_views(conn)
    refresh_top_researchers(conn)
    refresh_institution_ror(conn)
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
