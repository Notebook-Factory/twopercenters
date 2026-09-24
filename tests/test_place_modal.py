"""Clicking a place on the map, and then a row in its list.

A click on a city or a country opens a modal with that place's numbers, once;
closing it leaves the list of its researchers beside the map. Clicking a row
in the list opens a card over the map for that researcher or institution,
with links to where the record lives elsewhere: OpenAlex for a researcher
(only on a confident name match), ROR for an institution (only when the
institution was matched to the registry).
"""
import dash
import pytest
from dash.exceptions import PreventUpdate

from _dash_text import links_in, text_of

MATCHED_INSTITUTION = 'Stanford University'
UNMATCHED_INSTITUTION = 'College of Engineering'


class _Trigger:
    def __init__(self, triggered_id):
        self.triggered_id = triggered_id


@pytest.fixture
def home(monkeypatch):
    import app  # noqa: F401
    import pages.home as module

    def set_trigger(triggered_id):
        monkeypatch.setattr(module, 'callback_context', _Trigger(triggered_id))
    module.set_trigger = set_trigger
    return module


def _cambridge():
    from citations_lib.utils import city_points
    return next(p for p in city_points('career', 2024)
                if p['city'] == 'Cambridge' and p['country_code'] == 'US')


def _city_value(point):
    return f"city|{round(point['lat'], 3)}|{round(point['lng'], 3)}|1"


SHOWN = {'height': '560px', 'overflowY': 'auto', 'display': 'block'}
HIDDEN = {'height': '560px', 'display': 'none'}


# ------------------------------------------------------------- the modal

def test_a_country_click_opens_the_modal_with_its_numbers(home):
    home.set_trigger('glowPicked_glowmap_')
    summary, rows, _label, style, _cells, _active, is_open = \
        home.click_on_map_update('country|USA|2', True, '2024', 'median',
                                 HIDDEN)
    assert is_open is True
    text = text_of(summary)
    assert 'United States' in text
    assert 'Researchers on the list' in text
    assert 'H-index' in text
    assert rows and style['display'] == 'block'


def test_a_city_modal_shows_its_four_numbers(home):
    point = _cambridge()
    home.set_trigger('glowPicked_glowmap_')
    summary, _rows, _label, _style, _cells, _active, is_open = \
        home.click_on_map_update(_city_value(point), True, '2024', 'median',
                                 HIDDEN)
    assert is_open is True
    text = text_of(summary)
    assert 'Cambridge' in text
    for number in (point['researchers'], point['citations'],
                   point['papers'], point['h']):
        assert f'{number:,}' in text, number


def test_a_year_change_refreshes_the_modal_without_opening_it(home):
    home.set_trigger('glowYear_glowmap_')
    out = home.click_on_map_update('country|USA|2', True, '2023', 'median',
                                   SHOWN)
    assert out[-1] is dash.no_update
    assert 'United States' in text_of(out[0])


def test_the_close_icon_closes_the_modal(home):
    assert home.close_place_modal(1) is False
    with pytest.raises(PreventUpdate):
        home.close_place_modal(None)


def test_the_list_takes_the_place_of_the_explanation(home):
    """Before a click the pane explains the map. After one it is the list of
    that place, and the explanation goes rather than being pushed down."""
    assert home.explanation_style({'display': 'block'}) == {'display': 'none'}
    assert home.explanation_style({'display': 'none'}) == {}
    assert home.explanation_style(None) == {}


# ------------------------------------------------------------- the row card

def _usa_rows():
    from citations_lib.utils import country_researchers
    return country_researchers('usa', 'career', 2024, limit=5)


def test_a_researcher_row_opens_a_card_and_names_its_subject(home):
    rows = _usa_rows()
    card, subject = home.update_graphs(
        {'row': 0, 'column': 0, 'column_id': 'RESEARCHER'}, '2024', True,
        'median', rows, rows)
    name = rows[0]['RESEARCHER']
    text = text_of(card)
    assert name in text
    assert 'Citations' in text and 'H-index' in text
    assert subject == {'kind': 'researcher', 'name': name,
                       'author_id': rows[0]['AUTHOR_ID'], 'career': True,
                       'year': '2024'}


def test_an_institution_row_opens_a_card_and_names_its_subject(home):
    rows = [{'RESEARCHER': 'x', 'INSTITUTE': MATCHED_INSTITUTION}]
    card, subject = home.update_graphs(
        {'row': 0, 'column': 1, 'column_id': 'INSTITUTE'}, '2024', True,
        'median', rows, rows)
    text = text_of(card)
    assert MATCHED_INSTITUTION in text
    assert 'Researchers on the list' in text
    assert subject['kind'] == 'institution'
    assert subject['name'] == MATCHED_INSTITUTION


def test_a_researcher_gets_an_openalex_link_only_on_a_match(home,
                                                            monkeypatch):
    subject = {'kind': 'researcher', 'name': 'Ioannidis, John P.A.',
               'career': True, 'year': '2024'}
    monkeypatch.setattr(home, 'name_is_shared', lambda name: False)
    monkeypatch.setattr(home, 'openalex_author',
                        lambda name: 'https://openalex.org/A5000000001')
    assert 'https://openalex.org/A5000000001' in links_in(
        home.row_card_links(subject))

    monkeypatch.setattr(home, 'openalex_author', lambda name: None)
    links = links_in(home.row_card_links(subject))
    assert not any('openalex' in link for link in links)
    # The search link and the hand-off to Explore are there either way.
    assert any('scholar.google' in link for link in links)
    assert 'Open in Explore' in text_of(home.row_card_links(subject))


def test_an_institution_gets_a_ror_link_only_when_it_was_matched(home):
    matched = home.row_card_links({'kind': 'institution',
                                   'name': MATCHED_INSTITUTION})
    assert 'https://ror.org/00f54p054' in links_in(matched)

    unmatched = home.row_card_links({'kind': 'institution',
                                     'name': UNMATCHED_INSTITUTION})
    assert not any('ror.org' in link for link in links_in(unmatched))


def test_open_in_explore_hands_over_the_researcher_and_edition(home):
    subject = {'kind': 'researcher', 'name': 'Ioannidis, John P.A.',
               'career': True, 'year': '2024'}
    section, picked, preset = home.open_row_in_explore(1, subject)
    assert section == 'explore'
    assert picked == 'Ioannidis, John P.A.'
    assert preset == {'career': True, 'year': '2024', 'ns': False}
    with pytest.raises(PreventUpdate):
        home.open_row_in_explore(None, subject)


def test_institution_ror_lookup():
    from citations_lib.utils import institution_ror_for
    record = institution_ror_for(MATCHED_INSTITUTION)
    assert record['ror_id'] == 'https://ror.org/00f54p054'
    assert record['city'] == 'Stanford'
    assert institution_ror_for(UNMATCHED_INSTITUTION) is None
    assert institution_ror_for(None) is None


# ------------------------------------------------------------- the right person

# Five author_ids share this name. The list shows the one in the edition and
# place asked for; looking the name up again used to pick another of them,
# one with no career rows, and the card said "no record".
SHARED_NAME = 'Kim, Tae-kyun'


def _kim_row():
    from citations_lib.utils import country_researchers
    rows = country_researchers('kor', 'career', 2024)
    return next(r for r in rows if r['RESEARCHER'] == SHARED_NAME)


def test_list_rows_carry_the_author_id_they_came_from():
    from citations_lib.utils import city_researchers, country_researchers
    assert all(r.get('AUTHOR_ID') for r in
               country_researchers('usa', 'career', 2024, limit=5))
    point = _cambridge()
    rows, _total = city_researchers(round(point['lat'], 3),
                                    round(point['lng'], 3), 'career', 2024,
                                    limit=5)
    assert all(r.get('AUTHOR_ID') for r in rows)


def test_the_table_shows_only_the_two_columns(home):
    assert [c['id'] for c in home.tbl.columns] == ['INSTITUTE', 'RESEARCHER']


def test_a_shared_name_in_the_list_opens_that_researcher(home):
    from citations_lib.utils import _fetch
    row = _kim_row()
    card, subject = home.update_graphs(
        {'row': 0, 'column': 1, 'column_id': 'RESEARCHER'}, '2024', True,
        'median', [row], [row])
    text = text_of(card)
    assert 'no record' not in text.lower()
    nc = _fetch("select nc from career_metrics where author_id = %s "
                "and edition_id = 'career-2024'", (row['AUTHOR_ID'],))[0][0]
    assert f'{int(nc):,}' in text
    assert subject['author_id'] == row['AUTHOR_ID']


def test_a_name_prefers_a_researcher_with_a_career_record():
    """Career is the dataset the dashboard opens on. Resolving a name to a
    single-year-only researcher left every career view empty."""
    from citations_lib.utils import _author_ids_named, one_researcher
    chosen = one_researcher(tuple(sorted(_author_ids_named(SHARED_NAME))))
    assert 'career' in chosen


def test_a_shared_name_gets_no_openalex_link(home, monkeypatch):
    """OpenAlex is searched by name; with five researchers of one name a
    match says nothing about which of them it is."""
    monkeypatch.setattr(home, 'openalex_author',
                        lambda name: 'https://openalex.org/A5000000001')
    links = links_in(home.row_card_links(
        {'kind': 'researcher', 'name': SHARED_NAME, 'career': True,
         'year': '2024'}))
    assert not any('openalex' in link for link in links)


# ------------------------------------------------------------- the notes

def test_the_notes_beside_the_map(home):
    from _dash_text import walk
    notes = home.map_notes
    sections = [n for n in walk(notes) if type(n).__name__ == 'Details']
    titles = [text_of(n.children[0]).strip() for n in sections]
    assert not any('How to use the map' in t for t in titles)
    # The one note people most need is open from the start, and only it.
    assert [t for t, n in zip(titles, sections) if n.open] == \
        ['Career vs single year']
    # The composite score, which used to sit under the Explore card, with
    # the formula the code actually uses: log(1 + x) over log(1 + max).
    composite = next(n for t, n in zip(titles, sections)
                     if 'composite score' in t.lower())
    maths = [n for n in walk(composite) if getattr(n, 'mathjax', False)]
    assert maths and '1 +' in text_of(maths[0])
