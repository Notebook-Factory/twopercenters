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
    printed = row.children[2].children[2].children[1].children
    assert printed.endswith('% self-cited')
    assert abs(float(printed.split('%')[0]) - payload['self_pct'][0]) < 0.05


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
        assert module._open_in_explore([3], '') == ('explore', 'Wang, Zhong Lin')

        # A small chart writes the name into the hidden input instead.
        module.callback_context = _Context('top10Picked_top10_', 'He, Kaiming')
        assert module._open_in_explore([0], 'He, Kaiming') == ('explore',
                                                               'He, Kaiming')
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
            module._open_in_explore([0] * 10, '')
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
