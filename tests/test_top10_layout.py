"""The Top 10 tab's payloads.

The charts are drawn in the browser, so what can be tested here is what is
handed to them. The one that matters is the stacked bar: it claims to be the
published composite score taken apart, and it is only worth drawing if the
parts add back up.
"""
import pytest

from citations_lib.top10 import (composite_rows, composite_stack_payload,
                                 metric_grid_payload, top10_layout)
from citations_lib.utils import top_researchers


def test_the_six_segments_sum_to_the_published_score():
    payload = composite_stack_payload('career', 2024, False)
    for index, total in enumerate(payload['totals']):
        stacked = sum(series['data'][index] for series in payload['series'])
        assert stacked == pytest.approx(total, abs=1e-6)


def test_the_stack_is_in_the_published_order():
    payload = composite_stack_payload('career', 2024, False)
    assert payload['positions'] == list(range(1, 11))
    assert payload['totals'] == sorted(payload['totals'], reverse=True)
    assert len(payload['names']) == 10
    assert len(payload['series']) == 6


def test_career_2018_is_drawn_but_not_claimed_to_reproduce():
    """The one edition whose published scores cannot be recomputed from its
    recorded maxima. The six terms are still each metric's share of the
    edition maximum, so they are drawn; what is not true of them is that they
    sum to the number printed beside them, and the tab has to say so."""
    assert composite_stack_payload('career', 2018, False)['reproducible'] is False
    assert composite_stack_payload('career', 2024, False)['reproducible'] is True


def test_every_indicator_gets_ten_researchers_and_a_shared_flag():
    payload = metric_grid_payload('career', 2024, False)
    assert len(payload['charts']) == 6
    for chart in payload['charts']:
        assert len(chart['names']) == 10
        assert len(chart['shared']) == 10
        assert chart['values'] == sorted(chart['values'], reverse=True)


def test_the_shared_flag_marks_the_composite_top_ten():
    best = {row['author_id'] for row in top_researchers('career', 2024, 'c')}
    payload = metric_grid_payload('career', 2024, False)
    for chart in payload['charts']:
        for author_id, shared in zip(chart['author_ids'], chart['shared']):
            assert shared == (author_id in best)


def test_the_layout_builds_without_touching_the_database():
    """Built at import time on every worker, so it must not hold a query."""
    assert top10_layout() is not None


def _home():
    """pages/home.py registers itself as a Dash page, which needs an app to
    have been instantiated first. Importing app is also the stronger test:
    it builds every section's layout, so a section that cannot be built
    fails here rather than in a browser."""
    import app  # noqa: F401
    import pages.home as home
    return home


def test_the_top_ten_section_is_on_the_page():
    assert 'top10' in [section[0] for section in _home().ACCORDION_SECTIONS]


def test_every_section_has_a_navbar_button():
    """The jump buttons are keyed by item_id rather than by position, because
    reordering the sections used to silently repoint them."""
    home = _home()
    assert (set(home._JUMP_TARGETS.values())
            == {section[0] for section in home.ACCORDION_SECTIONS})


def test_the_scroll_handler_knows_where_every_section_sits():
    """The smooth-scroll handler carries its own button-to-position map. A
    stale one scrolls to the wrong section, silently, which is the bug the
    jump targets above were already rewritten once to avoid."""
    home = _home()
    source = home.__file__
    with open(source) as handle:
        text = handle.read()
    order = text.split("var order = {")[1].split("};")[0]
    for index, (item_id, *_rest) in enumerate(home.ACCORDION_SECTIONS):
        button = next(name for name, target in home._JUMP_TARGETS.items()
                      if target == item_id)
        assert f"'{button}': {index}" in order.replace('\n', ' ')


def test_a_ranked_row_carries_the_researcher_it_opens():
    """The row's id is how a click says who was clicked. It carries the name,
    because the name is what Explore is keyed on, so the callback does not
    have to look anything up and cannot look the wrong thing up."""
    payload = composite_stack_payload('career', 2024, False)
    rows = composite_rows(payload)
    assert len(rows) == 10
    assert [row.id['index'] for row in rows] == payload['names']
    assert all(row.id['type'] == 'top10-row' for row in rows)


def test_a_row_shows_a_flag_and_a_self_citation_share():
    payload = composite_stack_payload('career', 2024, False)
    row = composite_rows(payload)[0]
    flag = row.children[1]
    assert flag.src.endswith('/' + payload['flags'][0])
    assert flag.alt == payload['countries'][0]
    # The number only: "self-cited" printed after each of the ten was the
    # same two words ten times over. The legend says it once.
    printed = row.children[2].children[2].children[1].children
    assert printed.endswith('%')
    assert 'self' not in printed
    assert abs(float(printed.rstrip('%')) - payload['self_pct'][0]) < 0.05


def test_the_self_citation_share_is_a_percentage():
    """The column is a fraction in the fact table and a percentage on the
    Explore card, which reads that figure from Elasticsearch. Printing the
    fraction here would put 0.1% beside Explore's 14.26% for one researcher."""
    payload = composite_stack_payload('career', 2024, False)
    shares = [s for s in payload['self_pct'] if s is not None]
    assert shares
    assert any(share > 1 for share in shares)
    assert all(0 <= share <= 100 for share in shares)


def test_the_rows_and_the_chart_agree_on_row_height():
    """The names are HTML beside the chart, so the alignment between them is
    CSS on one side and an echarts constant on the other. They have to be the
    same two numbers."""
    import re

    from citations_lib.top10 import COMPOSITE_DRAW_JS
    row, top = re.search(r'var ROW = (\d+), TOP = (\d+);',
                         COMPOSITE_DRAW_JS).groups()
    with open('assets/style.css') as handle:
        css = handle.read()
    listing = css[css.index('.ev-top10-rows'):css.index('.ev-top10-composite')]
    assert f'padding-top: {top}px' in listing
    assert f'height: {row}px' in listing


def test_every_chart_on_the_tab_has_something_drawing_it():
    """Two charts, two clientside callbacks. One of these was registered by a
    function that was imported and never called, which leaves an empty space
    where the bars belong and no error anywhere to say so."""
    import app  # noqa: F401
    from dash._callback import GLOBAL_CALLBACK_MAP

    from citations_lib.top10 import SUFFIX
    for sink in ('top10CompositeSink', 'top10GridSink'):
        assert any(sink + SUFFIX in key for key in GLOBAL_CALLBACK_MAP), sink


def test_a_click_opens_that_researcher_in_explore():
    """There is no card on this tab. A click hands the name to Explore, which
    is where the full card already lives."""
    import citations_lib.top10 as module

    class _Context:
        def __init__(self, trigger, value):
            self.triggered_id = trigger
            self.triggered = [{'prop_id': 'x', 'value': value}]

    original = module.callback_context
    try:
        module.callback_context = _Context(
            {'type': 'top10-row', 'index': 'Wang, Zhong Lin'}, 3)
        where, name, preset = module._open_in_explore(
            [3], '', True, '2024', False)
        assert (where, name) == ('explore', 'Wang, Zhong Lin')
        # The edition travels with the name, or Explore opens on the earliest
        # year this researcher appears in rather than the one on screen.
        assert preset == {'career': True, 'year': '2024', 'ns': False}

        # A small chart writes the name into the hidden input instead.
        module.callback_context = _Context('top10Picked_top10_', 'He, Kaiming')
        where, name, preset = module._open_in_explore(
            [0], 'He, Kaiming', False, '2019', True)
        assert (where, name) == ('explore', 'He, Kaiming')
        assert preset == {'career': False, 'year': '2019', 'ns': True}
    finally:
        module.callback_context = original


def test_a_rebuilt_row_is_not_a_click():
    """Changing the picker replaces all ten rows, and Dash reports a newly
    rendered row as the trigger with n_clicks of 0. Treating that as a click
    would throw the reader into Explore for a name they never clicked."""
    import pytest as _pytest
    from dash.exceptions import PreventUpdate

    import citations_lib.top10 as module

    class _Context:
        def __init__(self, value):
            self.triggered_id = {'type': 'top10-row', 'index': 'Kresse, Georg'}
            self.triggered = [{'prop_id': 'x', 'value': value}]

    original = module.callback_context
    try:
        module.callback_context = _Context(0)
        with _pytest.raises(PreventUpdate):
            module._open_in_explore([0] * 10, '', True, '2024', False)
    finally:
        module.callback_context = original


def test_a_name_in_the_grid_is_hoverable():
    """The instruction under the grid says to hover a name. Only a bar fires
    mouseover unless the axis is told to raise events, so the names did
    nothing at all and the colours read as random."""
    from citations_lib.top10 import GRID_DRAW_JS
    assert 'triggerEvent: true' in GRID_DRAW_JS
    # An axis-label event carries the label text and no row index.
    assert "params.componentType === 'yAxis'" in GRID_DRAW_JS
    assert 'globalout' in GRID_DRAW_JS


def test_the_grid_legend_names_all_three_colours():
    """Three states, three colours: in the top ten overall, leading this
    indicator only, and the one being hovered."""
    layout = top10_layout()

    def walk(node):
        yield node
        children = getattr(node, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from walk(child)
        elif children is not None:
            yield from walk(children)

    classes = [getattr(n, 'className', '') or '' for n in walk(layout)]
    for key in ('ev-top10-key-shared', 'ev-top10-key-dim',
                'ev-top10-key-follow'):
        assert any(key in c for c in classes), key


def test_openalex_is_only_linked_when_the_name_actually_matches():
    """A search for a common surname returns the most cited match rather than
    the right one. A link to the wrong researcher is a claim this dashboard
    has no business making, so no match means no link."""
    from citations_lib.utils import _name_key, openalex_author
    assert _name_key('Ioannidis, John P.A.') == _name_key('John P. A. Ioannidis')
    assert _name_key('Smith, John A.') != _name_key('Smith, Jane B.')
    assert openalex_author('Qqqzzz, Nobody X.') is None


def test_the_openalex_lookup_survives_a_service_that_is_not_there():
    """It is somebody else's server, and the card has to render without it."""
    from citations_lib.utils import openalex_author
    assert openalex_author('Ioannidis, John P.A.', timeout=0.000001) is None
    assert openalex_author('') is None


def test_explore_opens_on_the_edition_that_was_clicked():
    """Explore lands on the earliest year an author appears in, which is
    right for a typed name and wrong for a researcher handed over from the
    top ten of career-2024."""
    import dash

    from citations_lib.auth_find import preset_choice
    options = [{'label': '2017', 'value': '2017'},
               {'label': '2024', 'value': '2024'}]
    preset = {'career': True, 'year': '2024', 'ns': False}

    # Pass one, the kind is already right: the year and the toggle are set
    # and the preset is spent.
    kind, year, ns, keep = preset_choice(options, preset, True)
    assert (kind, year, ns, keep) == (dash.no_update, '2024', False, None)


def test_a_preset_that_changes_the_kind_takes_two_passes():
    """Changing career to single-year rebuilds the year options, so the year
    cannot be set in the same pass. Clearing the preset there would leave the
    reader on the wrong year with nothing left to correct it."""
    import dash

    from citations_lib.auth_find import preset_choice
    preset = {'career': False, 'year': '2022', 'ns': True}
    kind, year, ns, keep = preset_choice([], preset, True)
    assert kind is False and year is dash.no_update and keep == preset

    options = [{'label': '2022', 'value': '2022'}]
    kind, year, ns, keep = preset_choice(options, preset, False)
    assert year == '2022' and ns is True and keep is None


def test_a_year_the_author_does_not_have_is_left_alone():
    """A researcher in the career top ten need not have a single-year row for
    the same year. Selecting it anyway would show an empty card."""
    import dash

    from citations_lib.auth_find import preset_choice
    options = [{'label': '2017', 'value': '2017'},
               {'label': '2024', 'value': '2024', 'disabled': True}]
    _kind, year, _ns, keep = preset_choice(
        options, {'career': True, 'year': '2024'}, True)
    assert year is dash.no_update
    assert keep is None


def test_without_a_preset_nothing_moves():
    """Typing a name into Explore must still land on the earliest year."""
    from dash.exceptions import PreventUpdate
    import pytest as _pytest

    from citations_lib.auth_find import preset_choice
    with _pytest.raises(PreventUpdate):
        preset_choice([{'label': '2017', 'value': '2017'}], None, True)
