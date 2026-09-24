"""The Explore tab has to survive authors whose rows are missing pieces.

16,657 career rows have no country and 10,967 have no institution. Both
callbacks behind the Explore card used to assume every row had both, so
picking one of these researchers raised inside the callback and the card
stayed on whoever was there before. The examples below are real rows in the
development database:

* "Craig, Arthur D.Bud" in career-2024 has an institution but no country.
* "Richardson, Janet Steven" in career-2018 has a country (gbr) but no
  institution.
* "Smith, Grant D." in career-2024 has neither.

The last group of tests is about the number of values each return path
hands back. Dash matches return values to outputs by position, so a path
that returns one too many or one too few raises for the whole callback.
"""
import pytest
from dash.exceptions import PreventUpdate

EXPLORE = '2author_figs_author_find_'
CARDS = 'InfoAuthor1_author_find_'
KINDS = 'careerORSingleYrA1_author_find_.options'

EXPLORE_OUTPUTS = 12
# Positions in the Explore callback's return value.
STORE, SHARE, LEGEND, BULLETS = 1, 8, 9, 10
UNKNOWN = 'Nobody, Xyzzy Q.'

NO_COUNTRY = 'Craig, Arthur D.Bud'
NO_INSTITUTION = 'Richardson, Janet Steven'
NEITHER = 'Smith, Grant D.'


def _explore(dash_callback, name, year, uplim='cntry', career=True):
    return dash_callback(EXPLORE)(career, year, False, name, uplim)


def _card_text(card):
    """The one line of text inside a fact card: Card > Center > str."""
    return card.children.children


# =============== Bug 1: no country

def test_explore_card_for_an_author_with_no_country(dash_callback):
    out = _explore(dash_callback, NO_COUNTRY, '2024')
    assert len(out) == EXPLORE_OUTPUTS
    share = out[SHARE]
    # Missing, not the string "None" and not a made-up country.
    assert share['country'] == ''
    assert share['institute'] == 'Deceased'
    # The default comparison is by country, and there is no country to
    # compare against, so no group band and no legend naming one.
    assert out[BULLETS]['reference'] is False
    assert out[LEGEND] == []


def test_fact_cards_for_an_author_with_no_country(dash_callback):
    out = dash_callback(CARDS)('2024', NO_COUNTRY, True)
    assert len(out) == 5
    line = _card_text(out[1])
    assert 'None' not in line
    assert line.startswith('Deceased, ')


# =============== Bug 2: no institution

def test_fact_cards_for_an_author_with_no_institution(dash_callback):
    out = dash_callback(CARDS)('2018', NO_INSTITUTION, True)
    line = _card_text(out[1])
    assert 'None' not in line
    assert not line.startswith(',')
    assert line.endswith('United Kingdom')


def test_fact_cards_for_an_author_with_neither(dash_callback):
    out = dash_callback(CARDS)('2024', NEITHER, True)
    assert _card_text(out[1]) == 'Physics & Astronomy'


# =============== Bug 3: comparing against an institution that is not there

def test_institution_comparison_without_an_institution(dash_callback):
    out = _explore(dash_callback, NO_INSTITUTION, '2018', uplim='inst_name')
    assert len(out) == EXPLORE_OUTPUTS
    bullets = out[BULLETS]
    assert bullets['reference'] is False
    assert bullets['group'] == ''
    assert out[LEGEND] == []
    # The bars themselves are still drawn, against the edition maximum.
    assert bullets['rows']
    assert all(row['median'] is None for row in bullets['rows'])
    # The what-if calculator reads its reference marks from the store, so
    # it has to carry the same absence rather than a stale group.
    assert out[STORE]['group_label'] == ''


@pytest.mark.parametrize('on', [False, True])
def test_what_if_keeps_the_comparison_unavailable(dash_callback, on):
    """The what-if callback redraws the bars from the store, on and off.
    It must not bring back a band the Explore callback left out."""
    state = _explore(dash_callback, NO_INSTITUTION, '2018',
                     uplim='inst_name')[STORE]
    typed = [None] * 6
    out = dash_callback('whatIf-c_author_find_')(on, *typed, state)
    assert out[0]['reference'] is False


def test_a_real_group_still_gets_its_band(dash_callback):
    """The guard for the two cases above must not switch off the band for
    everyone else."""
    out = _explore(dash_callback, NO_INSTITUTION, '2018', uplim='cntry')
    assert out[BULLETS]['reference'] is True
    assert out[BULLETS]['group'] == 'United Kingdom'
    assert any(row['median'] is not None for row in out[BULLETS]['rows'])


# =============== Bug 4: one value per output on every path

def test_explore_with_no_author_returns_one_value_per_output(dash_callback):
    out = _explore(dash_callback, None, '2024')
    assert len(out) == EXPLORE_OUTPUTS


def test_explore_with_a_name_that_finds_nobody(dash_callback):
    out = _explore(dash_callback, UNKNOWN, '2024')
    assert len(out) == EXPLORE_OUTPUTS


def test_kind_toggle_with_a_name_that_finds_nobody(dash_callback):
    out = dash_callback(KINDS)(UNKNOWN)
    assert len(out) == 2


def test_fact_cards_with_a_name_that_finds_nobody(dash_callback):
    with pytest.raises(PreventUpdate):
        dash_callback(CARDS)('2024', UNKNOWN, True)


def test_year_picker_with_a_name_that_finds_nobody(dash_callback):
    with pytest.raises(PreventUpdate):
        dash_callback('selectYrRadioA1_author_find_.options')(True, UNKNOWN)


@pytest.mark.parametrize('group', ['cntry', 'sm-field', 'inst_name'])
def test_a_missing_group_has_no_aggregate(group):
    """A row with no country or institution names no group, so there is
    nothing to summarise. Asking must answer that, not raise."""
    from citations_lib.utils import get_es_aggregate
    assert get_es_aggregate(group, None, 'career') == {}


# =============== What the card carries

def test_the_formula_is_not_under_the_card(callback_map):
    """It moved to the notes beside the map, which explain the data."""
    assert not any('c_score_formula_author_find_' in key
                   for key in callback_map)


def test_the_what_if_instructions_are_not_under_the_card(dash_callback):
    from _dash_text import text_of
    out = _explore(dash_callback, 'Ioannidis, John P.A.', '2024')
    assert 'Change any of the six numbers' not in text_of(out[0])
