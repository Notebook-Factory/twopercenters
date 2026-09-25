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


def test_switching_what_if_on_changes_nothing_on_its_own():
    """The boxes show hm rounded to one decimal, because a fractional
    h-index in a box needs to be readable. The recompute read the boxes, so
    turning what-if on quietly swapped 8.971429 for 9.0 and re-ranked
    against everyone else's exact figure: around rank 100,000, where the
    list is dense, 40 of 41 researchers moved, one of them by 174 places."""
    from citations_lib.auth_find import WHATIF_METRICS, box_value
    from citations_lib.utils import composite_score

    actual = {'nc': 284984.0, 'h': 231.0, 'hm': 147.8929716577942,
              'ncs': 12000.0, 'ncsf': 40000.0, 'ncsfl': 90000.0}
    maxima = {'nc': 500000.0, 'h': 300.0, 'hm': 200.0,
              'ncs': 50000.0, 'ncsf': 90000.0, 'ncsfl': 150000.0}

    # What the boxes hold when the card is first drawn.
    typed = {metric: box_value(metric, actual[metric])
             for metric, _ in WHATIF_METRICS}
    assert typed['hm'] == 147.9          # tidied for display
    assert typed['nc'] == 284984         # and a count is a whole number

    # What the recompute makes of them: an untouched box means the number it
    # is displaying, not the display.
    values = {}
    for metric, _ in WHATIF_METRICS:
        entered = typed[metric]
        untouched = (entered is None
                     or float(entered) == box_value(metric, actual[metric]))
        values[metric] = actual[metric] if untouched else float(entered)
    assert values == actual
    assert composite_score(values, maxima) == composite_score(actual, maxima)


def test_an_edited_box_is_taken_at_its_word():
    """The guard above must not swallow a real edit."""
    from citations_lib.auth_find import box_value

    actual_hm = 147.8929716577942
    assert float(147.9) == box_value('hm', actual_hm)   # untouched
    assert float(150.0) != box_value('hm', actual_hm)   # edited


def test_the_boxes_commit_on_enter_rather_than_on_every_digit():
    """Typing 90000 was five round trips, each recomputing the score and
    re-ranking against the whole edition."""
    with open('citations_lib/auth_find.py') as handle:
        source = handle.read()
    assert 'debounce = True' in source
    assert 'debounce = False' not in source


def test_only_the_what_if_card_gets_drag_handles():
    """The Top 10 tab draws these same rows for a researcher nobody is
    editing, so it passes no channel and grows no handles."""
    from citations_lib.auth_find import bullet_payload

    rows = [{'key': 'nc', 'label': 'Citations', 'value': 10.0,
             'ceiling': 100.0, 'share': 0.5}]
    editable = bullet_payload(rows, 'France', whatif=True, published=rows,
                              drag='whatIfDrag_author_find_',
                              suffix='_author_find_')
    assert editable['drag'] == 'whatIfDrag_author_find_'
    assert editable['suffix'] == '_author_find_'

    read_only = bullet_payload(rows, '', reference=False)
    assert read_only['drag'] is None


def test_a_drag_is_one_recompute_and_the_bar_is_the_score_term():
    """Each bar is that indicator's term in the composite score,
    ln(v+1)/ln(ceiling+1), so dragging it is dragging the contribution and
    the value comes back out of the inverse. Nothing reaches the server
    until the handle is let go: a drag is one recompute, not one per pixel."""
    from citations_lib.auth_find import BULLET_DRAW_JS

    block = BULLET_DRAW_JS[BULLET_DRAW_JS.index('function handleFor('):]
    assert 'Math.exp(share * Math.log(row.ceiling + 1)) - 1' in BULLET_DRAW_JS
    assert "draggable: 'horizontal'" in block
    # The channel is written on release and nowhere else.
    ondrag = block[block.index('ondrag:'):block.index('ondragend:')]
    assert 'dispatchEvent' not in ondrag
    assert 'dispatchEvent' in block[block.index('ondragend:'):]
    # And a handle is only drawn where there is somewhere to report to.
    assert 'if (payload.drag && payload.rows.length)' in BULLET_DRAW_JS


def test_switching_what_if_on_keeps_the_published_rank():
    """career-2017 stores the composite score rounded to six decimals:
    5.193486 where the terms add up to 5.193485526. In a list of 105,026
    people somebody sits in that 5e-07 gap, so recomputing the rank from the
    parts moved this researcher from 60th to 61st before anything had been
    edited."""
    with open('citations_lib/auth_find.py') as handle:
        source = handle.read()
    assert 'untouched = all(values[metric] == state[\'actual\'][metric]' in source
    assert 'new_c, new_standing = published_c, standing' in source


def test_every_switch_says_what_it_does_with_an_icon():
    """The icon rides in the knob, the circle that slides when the switch is
    thrown. daq generates the class names on that button, so the stylesheet
    matches the part of the name daq controls rather than the hash it puts
    in front of it."""
    import glob

    labels = {'Exclude self-citations': 'ev-switch-selfcite',
              'Log transformed': 'ev-switch-log',
              'What if': 'ev-switch-whatif'}
    seen = set()
    for path in glob.glob('citations_lib/*.py'):
        with open(path) as handle:
            source = handle.read()
        # One chunk per switch: the call itself, not the lines around it,
        # which is what let this test read the next switch's label.
        for chunk in source.split('daq.BooleanSwitch(')[1:]:
            call = chunk[:400]
            for label, klass in labels.items():
                if f"'{label}'" in call or f'"{label}"' in call:
                    assert klass in call, f'{path}: {label} has no icon'
                    seen.add(label)
    assert seen == set(labels), f'not every switch was checked: {seen}'

    with open('assets/style.css') as handle:
        css = handle.read()
    # In the knob, the circle that slides, rather than beside the words.
    for klass in labels.values():
        assert f'.{klass} button[class*="__button"]::before' in css
    # The icons themselves: a flask for the calculator, quote marks for
    # citations, a rising line for a log axis.
    for mask in ('--ev-mask-flask', '--ev-mask-quote', '--ev-mask-trend'):
        assert mask in css


def test_the_handles_ring_until_something_is_moved():
    """A circle at the end of a bar is a small thing to notice, and nothing
    else on the card says the bars can be pulled."""
    from citations_lib.auth_find import BULLET_DRAW_JS, bullet_payload

    rows = [{'key': 'nc', 'label': 'Citations', 'value': 10.0,
             'ceiling': 100.0, 'share': 0.5}]
    ringing = bullet_payload(rows, 'France', whatif=True, published=rows,
                             drag='whatIfDrag_author_find_', pulse=True)
    assert ringing['pulse'] is True
    assert bullet_payload(rows, 'France')['pulse'] is False

    # Echarts' own ripple rather than an animation of ours, under the
    # handles and taking no clicks.
    assert "type: 'effectScatter'" in BULLET_DRAW_JS
    assert 'if (payload.pulse && payload.drag)' in BULLET_DRAW_JS
    # And it stops on the first drag rather than waiting for the server.
    ondrag = BULLET_DRAW_JS[BULLET_DRAW_JS.index('ondrag:'):]
    ondrag = ondrag[:ondrag.index('ondragend:')]
    assert 'pulseIndex = -1' in ondrag
