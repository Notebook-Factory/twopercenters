"""Matching 66,079 free-text institution names to ROR.

The published data records an institution as whatever string Scopus held,
plus a country, and nothing else: no city, no identifier, no registry. ROR
has all three. What it does not have is any way to be sure a name means the
organisation it looks like it means, so the rules here are built to refuse
rather than to guess, and the tests are mostly about what must NOT match.
"""
import pytest

from pipeline.ror_match import (build_index, choose, name_variants, normalize)


def _entry(ror_id, country, kind='ror_display', city='Somewhere'):
    return {'ror_id': ror_id, 'country': country, 'city': city,
            'lat': 1.0, 'lng': 2.0, 'kind': kind, 'ror_name': ror_id}


# ---------------------------------------------------------------------------
# Normalising
# ---------------------------------------------------------------------------

def test_accents_and_punctuation_do_not_stop_a_match():
    """The data holds "Universidad Tecnica Particular de Loja" and ROR holds
    "Universidad Técnica Particular de Loja"."""
    assert normalize('Universidad Técnica Particular de Loja') == \
        normalize('Universidad Tecnica Particular de Loja')
    assert normalize('St. Jude Children`s Hospital') == \
        normalize('St Jude Children\'s Hospital')


def test_a_leading_the_is_not_part_of_the_name():
    """ROR has "University of British Columbia" and the data has "The
    University of British Columbia". 710 researchers sat behind that word."""
    assert normalize('The University of British Columbia') == \
        normalize('University of British Columbia')


def test_ampersands_read_as_the_word():
    assert normalize('Ear & Eye Hospital') == normalize('Ear and Eye Hospital')


# ---------------------------------------------------------------------------
# Which spellings are worth trying
# ---------------------------------------------------------------------------

def test_the_full_name_is_always_tried_first():
    kinds = [kind for kind, _text in name_variants('University of Oxford')]
    assert kinds[0] == 'name'


def test_a_trailing_department_or_city_is_dropped_on_the_second_try():
    """"Indian Institute of Technology Roorkee, Department of Chemistry" is
    an institution this registry knows plus a unit it does not."""
    variants = dict((kind, text) for kind, text in name_variants(
        'Indian Institute of Technology Roorkee, Department of Chemistry'))
    assert variants['prefix'] == normalize('Indian Institute of Technology '
                                           'Roorkee')


def test_a_parent_before_a_dash_is_not_tried():
    """"ICAR - Central Institute of Freshwater Aquaculture" would match the
    Indian Council of Agricultural Research, whose city is New Delhi and whose
    institute is in Bhubaneswar. The organisation is arguably right and the
    location is wrong, which is worse than no answer for a field whose whole
    purpose is location."""
    texts = [text for _kind, text in name_variants(
        'ICAR - Central Institute of Freshwater Aquaculture')]
    assert normalize('ICAR') not in texts


def test_a_name_with_nothing_to_trim_is_tried_once():
    assert len(name_variants('Stanford University')) == 1


# ---------------------------------------------------------------------------
# Choosing between candidates
# ---------------------------------------------------------------------------

def test_the_country_has_to_agree():
    """The published data's country is the one fact about the institution we
    already have. A candidate that contradicts it is the wrong organisation,
    whatever its name says."""
    assert choose([_entry('ror/a', 'gb')], 'us') is None
    assert choose([_entry('ror/a', 'us')], 'us')['ror_id'] == 'ror/a'


def test_two_organisations_of_the_same_name_in_one_country_are_refused():
    """"College of Engineering" is 1,109 researchers in career-2024 and is
    not an organisation. Picking one of several would put a city on a card
    that is simply invented."""
    assert choose([_entry('ror/a', 'us'), _entry('ror/b', 'us')], 'us') is None


def test_the_same_organisation_under_two_of_its_names_is_not_ambiguous():
    same = [_entry('ror/a', 'us', kind='alias'),
            _entry('ror/a', 'us', kind='ror_display')]
    chosen = choose(same, 'us')
    assert chosen['ror_id'] == 'ror/a'
    # The display name is the one to record, not whichever came first.
    assert chosen['kind'] == 'ror_display'


def test_an_institution_with_no_country_matches_nothing():
    """10,967 career rows carry no institution at all, and a name on its own
    is not enough to identify one."""
    assert choose([_entry('ror/a', 'us')], '') is None


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------

def test_every_name_a_record_is_known_by_is_indexed():
    records = [{
        'id': 'https://ror.org/x',
        'status': 'active',
        'names': [{'value': 'University of Vienna', 'types': ['ror_display',
                                                              'label']},
                  {'value': 'Universität Wien', 'types': ['label']},
                  {'value': 'UNIVIE', 'types': ['acronym']}],
        'locations': [{'geonames_details': {'country_code': 'AT',
                                            'name': 'Vienna',
                                            'lat': 48.2, 'lng': 16.3}}],
    }]
    index = build_index(records)
    for spelling in ('University of Vienna', 'Universitat Wien', 'UNIVIE'):
        assert normalize(spelling) in index, spelling
    entry = index[normalize('University of Vienna')][0]
    assert entry['country'] == 'at'
    assert entry['city'] == 'Vienna'
    assert entry['ror_name'] == 'University of Vienna'


def test_a_withdrawn_record_is_not_indexed():
    """ROR withdraws records. Matching one would attach an identifier that
    the registry itself no longer stands behind."""
    records = [{
        'id': 'https://ror.org/gone',
        'status': 'withdrawn',
        'names': [{'value': 'Gone University', 'types': ['ror_display']}],
        'locations': [{'geonames_details': {'country_code': 'US',
                                            'name': 'Nowhere',
                                            'lat': 0.0, 'lng': 0.0}}],
    }]
    assert build_index(records) == {}


def test_a_closed_organisation_is_still_indexed():
    """ROR marks an organisation that has closed or merged as inactive. This
    data is historical: a 2017 affiliation to an institute that has since
    closed was a real affiliation, and dropping those records cost about 700
    institutions for no gain in correctness."""
    records = [{
        'id': 'https://ror.org/closed',
        'status': 'inactive',
        'names': [{'value': 'Closed Institute', 'types': ['ror_display']}],
        'locations': [{'geonames_details': {'country_code': 'DE',
                                            'name': 'Jena',
                                            'lat': 50.9, 'lng': 11.6}}],
    }]
    assert normalize('Closed Institute') in build_index(records)


# ---------------------------------------------------------------------------
# What ended up in the database
# ---------------------------------------------------------------------------

def test_every_stored_match_agrees_with_the_published_country():
    """The rule the matcher is built on, checked against what it actually
    wrote rather than against itself."""
    from citations_lib.utils import _fetch, iso2
    rows = _fetch('select i.country_code, r.country_code '
                  'from institution_ror r '
                  'join institutions i on i.institution_id = r.institution_id')
    assert rows
    wrong = [(ours, theirs) for ours, theirs in rows
             if iso2(ours) != (theirs or '')]
    assert not wrong, wrong[:5]


def test_a_stored_match_carries_somewhere_to_point_at():
    from citations_lib.utils import _fetch
    rows = _fetch('select count(*) from institution_ror '
                  'where ror_id is null or city is null '
                  'or lat is null or lng is null')
    assert rows[0][0] == 0


def test_only_the_two_intended_spellings_were_used():
    from citations_lib.utils import _fetch
    kinds = {row[0] for row in
             _fetch('select distinct matched_on from institution_ror')}
    assert kinds <= {'name', 'prefix'}


def test_coverage_has_not_collapsed():
    """Floors, not targets. A new ROR release moves these by a little; a
    change to the matcher that breaks it moves them by a lot, and the point
    of the numbers is to notice that."""
    from citations_lib.utils import _fetch
    institutions = _fetch('select count(*) from institutions')[0][0]
    matched = _fetch('select count(*) from institution_ror')[0][0]
    assert matched / institutions > 0.25, f'{matched}/{institutions}'

    covered, total = _fetch(
        "select count(*) filter (where r.institution_id is not null), "
        "count(*) from career_metrics m "
        "left join institution_ror r on r.institution_id = m.institution_id "
        "where m.edition_id = 'career-2024'")[0]
    assert covered / total > 0.60, f'{covered}/{total}'


def _record(ror_id, name, status='active', city='Nowhere', country='US',
            successor=None):
    record = {
        'id': ror_id, 'status': status,
        'names': [{'value': name, 'types': ['ror_display']}],
        'locations': [{'geonames_details': {'country_code': country,
                                            'name': city,
                                            'lat': 1.0, 'lng': 2.0}}],
    }
    if successor:
        record['relationships'] = [{'type': 'successor', 'id': successor}]
    return record


def test_a_withdrawn_record_resolves_to_its_successor():
    """ROR withdrew the record for Harvard Medical School and named Harvard
    University as its successor. That is the registry's own statement about
    where the organisation went, and it is 1,014 researchers in career-2024,
    the largest matched institution on the list."""
    records = [_record('https://ror.org/new', 'Harvard University',
                       city='Cambridge'),
               _record('https://ror.org/old', 'Harvard Medical School',
                       status='withdrawn', city='Boston',
                       successor='https://ror.org/new')]
    index = build_index(records)
    entry = choose(index[normalize('Harvard Medical School')], 'us')
    assert entry['ror_id'] == 'https://ror.org/new'
    # The city is the successor's, which is a real if small error: the school
    # is in Boston and the university is in Cambridge. The flag is how a
    # consumer that cannot accept that filters it out.
    assert entry['city'] == 'Cambridge'
    assert entry['via_successor'] is True
    assert choose(index[normalize('Harvard University')], 'us')['via_successor'] \
        is False


def test_a_withdrawn_record_with_nowhere_to_go_is_dropped():
    records = [_record('https://ror.org/gone', 'Gone University',
                       status='withdrawn')]
    assert build_index(records) == {}


def test_a_successor_that_is_itself_withdrawn_is_not_followed():
    """Otherwise a chain of retractions ends at an identifier ROR does not
    stand behind either."""
    records = [_record('https://ror.org/a', 'A University',
                       status='withdrawn', successor='https://ror.org/b'),
               _record('https://ror.org/b', 'B University',
                       status='withdrawn')]
    assert normalize('A University') not in build_index(records)


def test_an_empty_database_is_not_an_error(tmp_path):
    """The migrations run before the first edition is loaded, and the build
    fixtures create an empty schema on purpose. Reporting a percentage of
    nothing raised ZeroDivisionError and took the whole build down with it."""
    import json as _json

    from pipeline.ror_match import refresh_institution_ror

    dump = tmp_path / 'ror-data.json'
    dump.write_text(_json.dumps([_record('https://ror.org/x', 'Somewhere')]))

    class _Empty:
        """The smallest thing that answers like a connection with nothing in
        it: the table exists, and every query returns no rows."""

        def execute(self, sql, *args):
            class _Result:
                def fetchone(inner):
                    return (1,) if 'information_schema' in sql else (0, 0)

                def fetchall(inner):
                    return []
            return _Result()

        def cursor(self):
            class _Cursor:
                def __enter__(inner):
                    return inner

                def __exit__(inner, *exc):
                    return False

                def executemany(inner, *args):
                    return None
            return _Cursor()

        def commit(self):
            return None

    refresh_institution_ror(_Empty(), str(dump))
