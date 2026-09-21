"""Match the published institution names to the Research Organization Registry.

The published data records an institution as whatever string Scopus held,
plus a country: no city, no coordinates, no identifier, in any edition from
2017 to 2024. ROR has all of those for 137,398 organisations, so the missing
geography is a matching problem rather than a data problem.

What makes it a problem rather than a lookup is that the strings are free
text. Some are organisations ("University of Liverpool"), some are
organisations plus a unit ("Indian Institute of Technology Roorkee,
Department of Chemistry"), some are units whose parent is only implied ("MRC
Toxicology Unit"), and some are not organisations at all ("College of
Engineering", which 1,109 researchers in career-2024 give as their
affiliation).

So the rules here refuse rather than guess:

  - the country we already hold has to agree with the country ROR gives,
  - one name may not resolve to two organisations in that country,
  - and the only trimming allowed is dropping what follows a comma.

Dropping what precedes a dash was tried and removed. In a trial it matched
78 more institutions, and it matched them to their parent: "ICAR - Central
Institute of Freshwater Aquaculture" resolved to the Indian Council of
Agricultural Research, whose city is New Delhi, while the institute is in
Bhubaneswar. For a field whose whole purpose is location, a confident wrong
city is worse than none.

Measured against v2.12-2026-08-25 on the 66,079 institutions in this
database: 19,120 match (28.9%), which covers 160,224 of the 230,333
researchers in career-2024 (69.6%). 135 of those matches are through a
withdrawn record's successor. The gap between those two numbers is the
shape of the data. The names that match are the large institutions, and the
long tail that does not is departments, hospital wings and laboratory names.
The step prints both numbers on every run, because they move with each ROR
release.

Run by `make build-all` through pipeline/build_relational.py, or on its own:

    python pipeline/ror_match.py data_ror/v2.12-2026-08-25-ror-data.zip
"""
import glob
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from collections import defaultdict

# The name types ROR records, in the order they are preferred when one
# organisation is known by several. The display name is what a reader should
# see; an acronym is the weakest evidence that this is the right organisation
# at all.
NAME_TYPES = ('ror_display', 'label', 'alias', 'acronym')


def normalize(name):
    """A name reduced to what two spellings of it have in common.

    Accents go, because the data holds "Universidad Tecnica Particular de
    Loja" and ROR holds "Universidad Técnica Particular de Loja". Punctuation
    goes for the same reason. A leading "the" goes because ROR has
    "University of British Columbia" and the data has "The University of
    British Columbia", and 710 researchers in career-2024 sat behind that one
    word.
    """
    text = unicodedata.normalize('NFKD', str(name or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace('&', ' and ')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    text = ' '.join(text.split())
    return text[4:] if text.startswith('the ') else text


def name_variants(name):
    """The spellings of one institution worth trying, best first.

    Returns (kind, normalized) pairs. `name` is the string as recorded;
    `prefix` is what is left after dropping everything from the first comma,
    which is how this data writes a department or a campus: "Indian Institute
    of Technology Roorkee, Department of Chemistry", "Beaumont Hospital,
    Dublin". The organisation is what comes first.
    """
    variants = [('name', normalize(name))]
    head = str(name or '').split(',')[0]
    trimmed = normalize(head)
    if trimmed and trimmed != variants[0][1]:
        variants.append(('prefix', trimmed))
    return variants


def _entry_for(record):
    """The one row worth keeping about an organisation."""
    names = record.get('names') or []
    display = next((n['value'] for n in names
                    if 'ror_display' in n.get('types', [])), None)
    details = (record.get('locations') or [{}])[0].get('geonames_details') or {}
    return {'ror_id': record.get('id'),
            'ror_name': display,
            'country': (details.get('country_code') or '').lower(),
            'city': details.get('name'),
            'lat': details.get('lat'),
            'lng': details.get('lng')}


def build_index(records):
    """Every name every organisation is known by, normalized.

    Inactive records are kept. They are organisations that have closed or
    merged, and this data is historical: a researcher whose 2017 affiliation
    was an institute that no longer exists was affiliated with it all the
    same.

    Withdrawn records are different. ROR has retracted them, so their own id
    is not one to attach to anything, but 1,270 of the 1,417 name a
    successor, and that is the registry's own statement about where the
    organisation went rather than a guess. "Harvard Medical School" is one of
    them, and it is the largest matched institution in career-2024 at 1,014
    researchers: its successor is Harvard University.

    So a withdrawn record's names point at its successor, and the row is
    flagged, because the location then belongs to the successor. Harvard
    Medical School is in Boston and Harvard University is in Cambridge, which
    is a real if small error, and a consumer that cares can filter on the
    flag. A withdrawn record with no successor is dropped: there is nothing
    to point it at.
    """
    by_id = {}
    for record in records:
        if record.get('status') != 'withdrawn':
            by_id[record.get('id')] = _entry_for(record)

    index = defaultdict(list)

    def add(names, entry):
        for item in names:
            types = item.get('types') or []
            kind = next((t for t in NAME_TYPES if t in types), 'alias')
            index[normalize(item['value'])].append(dict(entry, kind=kind))

    for record in records:
        names = record.get('names') or []
        if record.get('status') != 'withdrawn':
            add(names, dict(by_id[record['id']], via_successor=False))
            continue
        successor = next((rel.get('id') for rel in
                          (record.get('relationships') or [])
                          if rel.get('type') == 'successor'), None)
        entry = by_id.get(successor)
        if entry:
            add(names, dict(entry, via_successor=True))
    return dict(index)


def choose(candidates, country):
    """The one organisation this name can only mean, or None.

    `country` is the ISO2 code for the country the published data records.
    It is the one fact about this institution we already hold, so a candidate
    that contradicts it is the wrong organisation whatever its name says, and
    a name with no country behind it identifies nothing.
    """
    if not country:
        return None
    same = [c for c in candidates if c['country'] == country]
    if not same or len({c['ror_id'] for c in same}) > 1:
        # Two organisations of this name in this country. "College of
        # Engineering" is not an organisation, and picking one of several
        # would put a city on the card that is simply invented.
        return None
    return sorted(same, key=lambda c: NAME_TYPES.index(c['kind']))[0]


def match_institutions(institutions, index, to_iso2):
    """Match (institution_id, name, iso3 country) rows against the index.

    Returns (matches, counts). `to_iso2` converts the published ISO3 code,
    which is what the fact tables carry, to the ISO2 code ROR uses.
    """
    matches = {}
    counts = defaultdict(int)
    for institution_id, name, country_code in institutions:
        country = to_iso2(country_code) if country_code else ''
        for kind, text in name_variants(name):
            candidates = index.get(text)
            if not candidates:
                continue
            chosen = choose(candidates, country)
            if chosen is None:
                counts['refused, not one organisation'] += 1
                break
            matches[institution_id] = dict(chosen, matched_on=kind)
            counts[f'matched on {kind}'] += 1
            break
        else:
            counts['no name in the registry'] += 1
    return matches, dict(counts)


def load_dump(path):
    """The records in a ROR data dump, from the zip or the unpacked JSON."""
    if path.endswith('.zip'):
        with zipfile.ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.endswith('.json'))
            with archive.open(name) as handle:
                return json.load(handle)
    with open(path) as handle:
        return json.load(handle)


def find_dump(directory='data_ror'):
    """The newest dump in `directory`, or None.

    By modification time rather than by filename. ROR's own releases are
    named v2.12-2026-08-25-ror-data.zip, which sorts correctly, but a file
    saved under any other name would sort anywhere and silently pick the
    wrong release.
    """
    found = (glob.glob(os.path.join(directory, '*.zip'))
             + glob.glob(os.path.join(directory, '*.json')))
    return max(found, key=os.path.getmtime) if found else None


def refresh_institution_ror(conn, path=None):
    """Fill institution_ror from a ROR dump (migration 013).

    Like the other refresh steps, this is a guarded no-op rather than an
    error when there is nothing to do: a host without the dump, or a database
    that has not applied 013, still finishes a build. The dump is not in git,
    for the same reason the citation data is not.
    """
    exists = conn.execute(
        "select 1 from information_schema.tables "
        "where table_schema = 'public' and table_name = 'institution_ror'"
    ).fetchone()
    if not exists:
        print("institution_ror does not exist yet; skipping", flush=True)
        return
    path = path or find_dump()
    if not path:
        print("no ROR dump under data_ror/; skipping. See README.", flush=True)
        return

    # Imported here rather than at module scope so the pure functions above
    # can be tested without a database or a country table.
    from citations_lib.utils import iso2

    started = time.time()
    records = load_dump(path)
    index = build_index(records)
    institutions = conn.execute(
        'select institution_id, inst_name, country_code from institutions'
    ).fetchall()
    matches, counts = match_institutions(institutions, index, iso2)

    conn.execute('truncate institution_ror')
    with conn.cursor() as cur:
        cur.executemany(
            'insert into institution_ror (institution_id, ror_id, ror_name, '
            'city, country_code, lat, lng, matched_on, name_type, '
            'via_successor, dump_version) '
            'values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            [(institution_id, m['ror_id'], m['ror_name'], m['city'],
              m['country'], m['lat'], m['lng'], m['matched_on'], m['kind'],
              bool(m.get('via_successor')), os.path.basename(path))
             for institution_id, m in matches.items()])
    conn.commit()

    total = len(institutions)
    print(f"matched {len(matches):,} of {total:,} institutions "
          f"({len(matches) / total * 100:.1f}%) against {path} "
          f"in {time.time() - started:.1f}s", flush=True)
    for key in sorted(counts):
        print(f"    {key:32} {counts[key]:>7,}", flush=True)
    # The number that matters is not how many names matched but how many
    # researchers those names cover: the institutions that match are the
    # large ones.
    covered = conn.execute(
        "select count(*) filter (where r.institution_id is not null), "
        "count(*) from career_metrics m "
        "left join institution_ror r on r.institution_id = m.institution_id "
        "where m.edition_id = ("
        "  select edition_id from editions where kind = 'career' "
        "  and superseded_by is null order by data_year desc limit 1)"
    ).fetchone()
    if covered and covered[1]:
        print(f"    {'researchers covered, newest career':32} "
              f"{covered[0]:>7,} of {covered[1]:,} "
              f"({covered[0] / covered[1] * 100:.1f}%)", flush=True)


def main(argv):
    from db.connection import connect
    path = argv[1] if len(argv) > 1 else None
    with connect() as conn:
        refresh_institution_ror(conn, path)


if __name__ == '__main__':
    main(sys.argv)
