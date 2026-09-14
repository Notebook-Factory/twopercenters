"""The exact-name fetch path, and the wrong-author bug it fixes.

Once the user has picked a name out of the typeahead dropdown, the dashboard
has that author's display name exactly and looks it up in Postgres
(`get_es_results(..., exact=True)`). It used to run the same fuzzy
Elasticsearch multi_match the typeahead runs, then take row 0 of a frame
sorted by edition count across every matched name. Row 0 is frequently
somebody else: asking for 'Muller, Markus' returned 'Mullner, Markus', and
asking for 'Garcia, David' returned 'Garcia, David A.'.

Nothing failed when that happened, which is the worst property a bug like
this can have: the dashboard drew another researcher's citation record under
the requested name. These tests fail if the exact path regresses to fuzzy, if
a miss silently falls back to fuzzy, or if es_result_pick goes back to
trusting row 0. The last test checks the other direction: the typeahead is
still fuzzy, so the fix did not buy correctness by making search worse.

The names used here were verified against the loaded database: 'Müller,
Markus' (19 author_ids share the display name), 'Müllner, Markus',
'Garcia, David', 'Garcia, David A.' and 'García-Dorado, David' all exist.
"""
import pytest

from citations_lib.utils import es_result_pick, get_es_results


def _names(frame):
    """The distinct display names a get_es_results frame carries."""
    if frame is None:
        return []
    return list(dict.fromkeys(frame['_source.authfull']))


# --------------------------------------------------- exact resolves exactly

def test_exact_lookup_resolves_muller_not_mullner():
    """'Müllner, Markus' is what the fuzzy path returned for this name."""
    frame = get_es_results('Müller, Markus', 'career', 'authfull', exact=True)
    assert _names(frame) == ['Müller, Markus']
    assert 'Müllner, Markus' not in _names(frame)


def test_exact_lookup_resolves_garcia_david():
    """The fuzzy path ranked 'Garcia, David A.' and 'García-Dorado, David'
    above the requested name and returned one of them."""
    frame = get_es_results('Garcia, David', 'career', 'authfull', exact=True)
    assert _names(frame) == ['Garcia, David']
    assert 'Garcia, David A.' not in _names(frame)
    assert 'García-Dorado, David' not in _names(frame)


def test_exact_data_is_the_requested_authors_record():
    """Whole-record check, not just the name: the two men have different
    careers, so a swap shows up in the editions and the institution."""
    muller = es_result_pick(
        get_es_results('Müller, Markus', 'career', 'authfull', exact=True),
        'data', None)
    mullner = es_result_pick(
        get_es_results('Müllner, Markus', 'career', 'authfull', exact=True),
        'data', None)
    assert muller and mullner
    assert muller != mullner
    # Müller, Markus is in seven career editions, Müllner, Markus in two.
    assert 'career_2017' in muller
    assert 'career_2017' not in mullner


def test_exact_data_for_garcia_david_is_not_garcia_david_a():
    garcia = es_result_pick(
        get_es_results('Garcia, David', 'career', 'authfull', exact=True),
        'data', None)
    garcia_a = es_result_pick(
        get_es_results('Garcia, David A.', 'career', 'authfull', exact=True),
        'data', None)
    assert garcia and garcia_a
    assert garcia != garcia_a


# ------------------------------------------------- a miss stays a miss

def test_exact_lookup_of_an_unknown_name_returns_nothing():
    """No silent fuzzy fallback. A fallback would hide exactly the mistake
    the exact path exists to surface."""
    frame = get_es_results('Zzzqqx, Notarealperson', 'career', 'authfull',
                           exact=True)
    assert frame is None
    assert es_result_pick(frame, 'data', None) is None


def test_a_near_miss_does_not_resolve_to_the_near_name():
    """'Müllner, Markus' exists; 'Müllnerr, Markus' does not. The exact path
    must not reach the former from the latter."""
    assert get_es_results('Müllnerr, Markus', 'career', 'authfull',
                          exact=True) is None


# ------------------------------------- es_result_pick will not take row 0

def test_pick_returns_the_requested_author_from_a_fuzzy_frame():
    """Even given a fuzzy frame whose row 0 is the wrong man, the pick hands
    back the requested author's record.

    The precondition says only that row 0 is somebody else, not who. It used
    to name `Müllner, Markus`, which made the test fail whenever the ranking
    moved for reasons that have nothing to do with what it checks: rebuilding
    the index on merged author identities and adding an affiliation clause to
    the query between them promoted `Keller, Markus` instead. Either one is a
    wrong author, which is all this needs."""
    fuzzy = get_es_results('Müller, Markus', 'career', 'authfull')
    assert fuzzy['_source.authfull'].iloc[0] != 'Müller, Markus', (
        'this test is only meaningful while row 0 is the wrong author')
    from_fuzzy = es_result_pick(fuzzy, 'data', None)
    from_exact = es_result_pick(
        get_es_results('Müller, Markus', 'career', 'authfull', exact=True),
        'data', None)
    assert from_fuzzy == from_exact


def test_pick_raises_rather_than_returning_a_stranger():
    """If the requested name is not in the frame at all, there is no honest
    answer to give, so it fails loudly instead of picking somebody."""
    frame = get_es_results('Müller, Markus', 'career', 'authfull')
    with pytest.raises(ValueError) as excinfo:
        es_result_pick(frame, 'data', None,
                       expect_name='Zzzqqx, Notarealperson')
    assert 'Zzzqqx, Notarealperson' in str(excinfo.value)


# ------------------------------------------- the typeahead is still fuzzy

def test_typeahead_still_matches_a_typo():
    """exact=False is unchanged: a mistyped name still finds the author."""
    frame = get_es_results('Müllr, Markus', ['career', 'singleyr'],
                           'authfull')
    assert 'Müller, Markus' in es_result_pick(frame, 'authfull')


def test_typeahead_typo_on_a_latin_name_too():
    frame = get_es_results('Grcia, David', ['career', 'singleyr'], 'authfull')
    names = es_result_pick(frame, 'authfull')
    assert 'Garcia, David' in names
    # Fuzziness is not narrowed to the one right answer: the neighbours the
    # exact path deliberately excludes are still offered as search results.
    assert 'Garcia, David A.' in names
