"""The Top 10 tab's payloads.

The charts are drawn in the browser, so what can be tested here is what is
handed to them. The one that matters is the stacked bar: it claims to be the
published composite score taken apart, and it is only worth drawing if the
parts add back up.
"""
import pytest

from citations_lib.top10 import (card_children, composite_stack_payload,
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


def test_the_card_draws_seven_rows_against_the_edition_maximum():
    top = top_researchers('career', 2024, 'c')[0]
    card = card_children(top['author_id'], 'career', 2024, False)
    payload = card['bullet']
    assert len(payload['rows']) == 7
    assert payload['reference'] is False
    assert payload['rows'][-1]['key'] == 'c'
    assert all(row['ceiling'] for row in payload['rows'])


def test_the_researcher_with_the_most_citations_fills_that_bar():
    """Their value is the edition maximum, so their share of it is 1. A card
    where that bar stopped short would mean the denominator is not the one
    the score uses."""
    top = top_researchers('career', 2024, 'nc')[0]
    payload = card_children(top['author_id'], 'career', 2024, False)['bullet']
    citations = next(r for r in payload['rows'] if r['key'] == 'nc')
    assert citations['share'] == 1.0


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
    """The row's id is how a click says who was clicked. Carrying the author
    id in the id itself means the callback does not have to look anything up,
    and cannot look the wrong thing up."""
    from citations_lib.top10 import composite_rows
    payload = composite_stack_payload('career', 2024, False)
    rows = composite_rows(payload)
    assert len(rows) == 10
    assert [row.id['index'] for row in rows] == payload['author_ids']
    assert all(row.id['type'] == 'top10-row' for row in rows)


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
