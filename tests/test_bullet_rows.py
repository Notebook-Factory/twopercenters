"""Each bar has to say what it is a share of.

The bars are drawn as ln(v+1)/ln(max+1) against the edition maximum, and the
only thing on screen that named the denominator was one axis tick reading
"edition max". That tick is the same for all six rows, so a reader could see
that citations reach three quarters of the way across without ever learning
that three quarters of the way across is 250,000 citations. The number has to
travel with the row.
"""
from citations_lib.auth_find import WHATIF_METRICS, bullet_rows

MAXIMA = {'nc': 250000.0, 'h': 232.0, 'hm': 81.0,
          'ncs': 40000.0, 'ncsf': 60000.0, 'ncsfl': 90000.0}
VALUES = {'nc': 1200.0, 'h': 20.0, 'hm': 12.0,
          'ncs': 300.0, 'ncsf': 500.0, 'ncsfl': 800.0}
QUARTILES = {metric: {'q1': 1.0, 'median': 2.0, 'q3': 3.0}
             for metric, _ in WHATIF_METRICS}


def test_every_indicator_row_carries_the_maximum_it_is_divided_by():
    rows = bullet_rows(VALUES, MAXIMA, QUARTILES)
    by_key = {row['key']: row for row in rows}
    for metric, _ in WHATIF_METRICS:
        assert by_key[metric]['ceiling'] == MAXIMA[metric]


def test_the_composite_row_tops_out_at_one_per_indicator():
    """The score's own ceiling is the six terms all at 1, which is 6. Drawing
    it on the same axis as the six is only honest if it says so."""
    rows = bullet_rows(VALUES, MAXIMA, QUARTILES, {'q1': 1, 'median': 2, 'q3': 3})
    assert rows[-1]['key'] == 'c'
    assert rows[-1]['ceiling'] == len(WHATIF_METRICS)


def test_a_card_with_no_comparison_group_says_so():
    """The Top 10 card draws a researcher against the edition maximum and
    against nothing else. Without this flag the median tick lands at zero,
    which reads as a real median of zero rather than as an absent one."""
    from citations_lib.auth_find import bullet_payload
    assert bullet_payload([], '', reference=False)['reference'] is False
    assert bullet_payload([], 'Canada')['reference'] is True


def test_rows_built_without_a_group_carry_no_median():
    """bullet_rows takes the quartiles from a dict it is handed. Handed an
    empty one it used to put 0 in every reference field, which the chart
    cannot tell apart from a group whose median really is zero."""
    rows = bullet_rows(VALUES, MAXIMA, {})
    assert rows
    for row in rows:
        assert row['median'] is None
        assert row['q1'] is None
        assert row['q3'] is None


def test_the_middle_half_band_is_not_the_colour_of_the_track():
    """The band and the track each bar runs in were both --ev-surface-2,
    drawn over a card in --ev-surface, which is a shade away. The band was
    there and could not be seen. It is drawn in the text colour now, faintly,
    which stands off the track in both themes."""
    import re
    from citations_lib.auth_find import BULLET_DRAW_JS
    band = re.search(r"var band = token\('(--ev-[a-z0-9-]+)'", BULLET_DRAW_JS)
    track = re.search(r"var track = token\('(--ev-[a-z0-9-]+)'", BULLET_DRAW_JS)
    assert band and track, 'band and track are named separately'
    assert band.group(1) != track.group(1)
    assert band.group(1) != '--ev-surface-2'
    assert 'backgroundStyle: {color: track' in BULLET_DRAW_JS
