"""The map's panel and the card over it, on the paths that used to raise.

Each test here reproduces one way the country and city panel on the home
page crashed or described something other than what the reader clicked. The
callbacks are called the way the browser calls them: the arguments are built
from the inputs and states the callback is registered with, by name, so a
test cannot pass a value the real callback would never be sent.
"""
import pytest
from dash.development.base_component import Component
from dash.exceptions import PreventUpdate

from _dash_text import text_of

import app  # noqa: F401  (registers the pages and their callbacks)
from pages import home


def _registered(output_fragment):
    """The callback_map entry whose output id contains the fragment."""
    app.server.test_client().get("/")
    keys = [key for key in app.app.callback_map if output_fragment in key]
    assert len(keys) == 1, (output_fragment, keys)
    return app.app.callback_map[keys[0]]


def call_as_dash(output_fragment, values):
    """Call a callback with `values`, a dict of 'id.property' to value.

    Anything the callback declares and the dict leaves out arrives as None,
    which is what Dash sends for a property the component has not set.
    Cards come back as the text a reader would see in them.
    """
    entry = _registered(output_fragment)
    declared = list(entry["inputs"]) + list(entry["state"])
    args = [values.get(f"{item['id']}.{item['property']}") for item in declared]
    result = entry["callback"].__wrapped__(*args)
    return tuple(text_of(r) if isinstance(r, Component) else r for r in result)


def card_for(values):
    """The text of the card a clicked row opens."""
    card, _subject = call_as_dash("row-detail.children", values)
    return card


class _Triggered:
    """callback_context only exists inside a request, so a direct call says
    which input fired."""
    def __init__(self, triggered_id):
        self.triggered_id = triggered_id


@pytest.fixture
def triggered(monkeypatch):
    def set_trigger(triggered_id):
        monkeypatch.setattr(home, "callback_context", _Triggered(triggered_id))
    return set_trigger


SHOWN = {'height': '560px', 'overflowY': 'auto', 'display': 'block'}


def _country_rows(code='usa', kind='career', year=2024, limit=60):
    return home.country_researchers(code, kind, year, limit=limit)


# ---------------------------------------------------------------------------
# 1. The clicked row is the row on screen
# ---------------------------------------------------------------------------

def test_a_click_on_the_second_page_reads_the_name_on_that_page():
    """active_cell['row'] counts the rows on screen, not the rows in `data`.
    The table pages at 20, so the first row of page two is data[20], and
    reading data[0] put another researcher's numbers in the card."""
    data = _country_rows()
    on_page_two = data[20:40]
    assert on_page_two[0]['RESEARCHER'] != data[0]['RESEARCHER']

    card = card_for({
        "instnametable.active_cell": {'row': 0, 'column': 1,
                                      'column_id': 'RESEARCHER'},
        "glowYear_glowmap_.value": 2024,
        "careerORSingleYrRadioHOME.value": True,
        "stats2.value": 'median',
        "instnametable.data": data,
        "instnametable.derived_viewport_data": on_page_two,
    })
    assert on_page_two[0]['RESEARCHER'] in card
    assert data[0]['RESEARCHER'] not in card


def test_a_click_after_sorting_reads_the_name_that_was_clicked():
    """Sorting reorders what is on screen and leaves `data` alone."""
    data = _country_rows()
    reversed_view = list(reversed(data))[:20]
    card = card_for({
        "instnametable.active_cell": {'row': 0, 'column': 1,
                                      'column_id': 'RESEARCHER'},
        "glowYear_glowmap_.value": 2024,
        "careerORSingleYrRadioHOME.value": True,
        "stats2.value": 'median',
        "instnametable.data": data,
        "instnametable.derived_viewport_data": reversed_view,
    })
    assert reversed_view[0]['RESEARCHER'] in card


# ---------------------------------------------------------------------------
# 2. The summaries say something instead of raising
# ---------------------------------------------------------------------------

def _institute_row():
    return next(r for r in _country_rows() if r['INSTITUTE'])


def test_an_institute_with_the_statistic_cleared_asks_for_one():
    """The statistic dropdown can be cleared, and then there is no column of
    the summary to read."""
    row = _institute_row()
    card = card_for({
        "instnametable.active_cell": {'row': 0, 'column': 0,
                                      'column_id': 'INSTITUTE'},
        "glowYear_glowmap_.value": 2024,
        "careerORSingleYrRadioHOME.value": True,
        "stats2.value": None,
        "instnametable.data": [row],
        "instnametable.derived_viewport_data": [row],
    })
    assert row['INSTITUTE'] in card
    assert 'statistic' in card.lower()


def test_a_country_with_the_statistic_cleared_still_lists_its_people(
        triggered):
    triggered('glowPicked_glowmap_')
    summary, rows, message, style, _cells, _active, _open = call_as_dash(
        "instnametable.data", {
            "glowPicked_glowmap_.value": 'country|NLD|3',
            "careerORSingleYrRadioHOME.value": True,
            "glowYear_glowmap_.value": '2024',
            "stats2.value": None,
            "instnametable.style_table": {'display': 'none'},
        })
    assert 'Netherlands' in summary
    assert 'statistic' in summary.lower()
    assert rows
    assert style['display'] == 'block'


def test_a_researcher_the_lookup_cannot_find_gets_a_message(monkeypatch):
    monkeypatch.setattr(home, "get_es_results", lambda *a, **k: None)
    row = {'INSTITUTE': 'Nowhere', 'RESEARCHER': 'Nobody, Anybody'}
    card = card_for({
        "instnametable.active_cell": {'row': 0, 'column': 1,
                                      'column_id': 'RESEARCHER'},
        "glowYear_glowmap_.value": 2024,
        "careerORSingleYrRadioHOME.value": True,
        "stats2.value": 'median',
        "instnametable.data": [row],
        "instnametable.derived_viewport_data": [row],
    })
    assert 'Nobody, Anybody' in card
    assert 'no record' in card.lower()


def test_a_column_with_no_detail_behind_it_changes_nothing():
    row = {'INSTITUTE': 'Somewhere', 'RESEARCHER': 'Someone, Anyone'}
    with pytest.raises(PreventUpdate):
        card_for({
            "instnametable.active_cell": {'row': 0, 'column': 2,
                                          'column_id': 'SOMETHING_ELSE'},
            "glowYear_glowmap_.value": 2024,
            "careerORSingleYrRadioHOME.value": True,
            "stats2.value": 'median',
            "instnametable.data": [row],
            "instnametable.derived_viewport_data": [row],
        })


def test_a_researcher_with_no_record_in_this_edition_gets_a_message():
    """A researcher listed in career 2024 need not have a single-year 2017
    record. The card says so instead of raising a KeyError."""
    from citations_lib.utils import es_result_pick, get_es_results
    name = None
    for row in _country_rows(limit=200):
        found = get_es_results(row['RESEARCHER'], 'career', 'authfull',
                               exact=True)
        data = es_result_pick(found, 'data', None)
        if data and 'career_2024' in data and 'career_2017' not in data:
            name = row['RESEARCHER']
            break
    assert name, 'no researcher here is new since 2017'
    row = {'INSTITUTE': '', 'RESEARCHER': name}
    card = card_for({
        "instnametable.active_cell": {'row': 0, 'column': 1,
                                      'column_id': 'RESEARCHER'},
        "glowYear_glowmap_.value": 2017,
        "careerORSingleYrRadioHOME.value": True,
        "stats2.value": 'median',
        "instnametable.data": [row],
        "instnametable.derived_viewport_data": [row],
    })
    assert name in card
    assert 'no record' in card.lower()


def test_an_institute_with_no_record_in_this_edition_gets_a_message():
    """An empty INSTITUTE cell, which country_researchers writes for a row
    with no institution, has no aggregate at all."""
    row = {'INSTITUTE': '', 'RESEARCHER': 'Someone, Anyone'}
    card = card_for({
        "instnametable.active_cell": {'row': 0, 'column': 0,
                                      'column_id': 'INSTITUTE'},
        "glowYear_glowmap_.value": 2024,
        "careerORSingleYrRadioHOME.value": True,
        "stats2.value": 'median',
        "instnametable.data": [row],
        "instnametable.derived_viewport_data": [row],
    })
    assert 'no record' in card.lower()


def test_a_country_in_an_edition_that_does_not_exist_gets_a_message(
        triggered):
    """There is no single-year 2018. Switching dataset with 2018 still on
    the track used to raise a KeyError out of the country summary."""
    triggered('careerORSingleYrRadioHOME')
    summary, rows, message, style, _cells, _active, _open = call_as_dash(
        "instnametable.data", {
            "glowPicked_glowmap_.value": 'country|USA|2',
            "careerORSingleYrRadioHOME.value": False,
            "glowYear_glowmap_.value": '2018',
            "stats2.value": 'median',
            "instnametable.style_table": SHOWN,
        })
    assert 'United States' in summary
    assert 'no record' in summary.lower()
    assert rows == []


# ---------------------------------------------------------------------------
# 3. The map stays on a year the dataset has
# ---------------------------------------------------------------------------

def test_switching_to_single_year_moves_the_track_off_2018():
    from citations_lib.glowmap import _rebuild_slider
    from citations_lib.utils import edition_years
    slider = _rebuild_slider(False, 2018)
    assert slider.value in edition_years('singleyr')
    # The nearest edition, not a jump to the other end of the track.
    assert slider.value == 2019


def test_the_map_is_drawn_for_a_year_the_dataset_has():
    """The toggle and the stale year reach the map's data together, before
    the rebuilt track has sent its new value, so the points have to be read
    for an edition that exists or the map draws empty."""
    from citations_lib.glowmap import _points
    payload = _points(2018, False)
    assert payload['lat']


def test_a_year_the_dataset_has_is_left_where_it_is():
    from citations_lib.glowmap import year_slider
    assert year_slider(False, 2021).value == 2021
    assert year_slider(True, 2018).value == 2018


# ---------------------------------------------------------------------------
# 4. After a year change the panel describes the year on the map
# ---------------------------------------------------------------------------

def _a_city_new_since(kind, year, earlier):
    from citations_lib.utils import city_points
    before = {(round(p['lat'], 3), round(p['lng'], 3))
              for p in city_points(kind, earlier)}
    return next((round(p['lat'], 3), round(p['lng'], 3))
                for p in city_points(kind, year)
                if (round(p['lat'], 3), round(p['lng'], 3)) not in before)


def test_a_city_with_nobody_in_the_new_edition_clears_the_panel(triggered):
    """Moving the year to an edition where the city has nobody used to raise
    PreventUpdate, which left the previous edition's list on screen beside a
    map of the new one."""
    lat, lng = _a_city_new_since('career', 2024, 2017)
    triggered('glowYear_glowmap_')
    summary, rows, message, style, _cells, _active, _open = call_as_dash(
        "instnametable.data", {
            "glowPicked_glowmap_.value": f'city|{lat}|{lng}|4',
            "careerORSingleYrRadioHOME.value": True,
            "glowYear_glowmap_.value": '2017',
            "stats2.value": 'median',
            "instnametable.style_table": SHOWN,
        })
    assert rows == []
    assert '2017' in message
    assert 'no researchers' in (summary + message).lower()
