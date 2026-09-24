"""Switching the what-if calculator on says where to type.

The six boxes beside the bars are read-only until what-if is on, and nothing
on the card said they had become editable. A tooltip opens on the Citations
box when it is switched on and closes on the first edit, after a few
seconds, or when it is switched off again.
"""
import pytest
from dash.exceptions import PreventUpdate

from _dash_text import text_of

TIP = 'whatIfTip_author_find_.is_open'
REPRODUCIBLE = {'reproducible': True}


class _Trigger:
    def __init__(self, triggered_id):
        self.triggered_id = triggered_id


@pytest.fixture
def tip(dash_callback, monkeypatch):
    import citations_lib.auth_find as module
    function = dash_callback(TIP)

    def call(trigger, on, n_intervals=0, state=REPRODUCIBLE):
        monkeypatch.setattr(module, 'callback_context', _Trigger(trigger))
        values = [None] * len(module.WHATIF_METRICS)
        return function(on, n_intervals, *values, state)
    return call


def test_switching_what_if_on_opens_the_tip(tip):
    is_open, timer_off, _ = tip('whatIfToggle_author_find_', True)
    assert is_open is True
    assert timer_off is False


def test_switching_it_off_closes_the_tip(tip):
    is_open, timer_off, _ = tip('whatIfToggle_author_find_', False)
    assert is_open is False
    assert timer_off is True


def test_the_tip_closes_by_itself(tip):
    is_open, timer_off, _ = tip('whatIfTipTimer_author_find_', True, 1)
    assert is_open is False and timer_off is True


def test_the_first_edit_closes_the_tip(tip):
    is_open, _timer_off, _ = tip('whatIf-nc_author_find_', True)
    assert is_open is False


def test_no_tip_where_the_calculator_is_off(tip):
    """An edition whose scores cannot be rebuilt keeps the boxes locked, so
    telling a reader to type into them would be wrong."""
    is_open, _timer_off, _ = tip('whatIfToggle_author_find_', True,
                                 state={'reproducible': False})
    assert is_open is False


def test_no_card_no_tip(tip):
    with pytest.raises(PreventUpdate):
        tip('whatIfToggle_author_find_', True, state=None)


def test_the_tip_sits_on_the_citations_box():
    import app  # noqa: F401
    import citations_lib.auth_find as module
    state = {'actual': {m: 10 for m, _ in module.WHATIF_METRICS},
             'maxima': {m: 100 for m, _ in module.WHATIF_METRICS},
             'np': 50}
    cells = module.bullet_inputs(state)
    tips = [c for c in cells if type(c).__name__ == 'Tooltip']
    assert len(tips) == 1
    assert tips[0].target == 'whatIf-nc_author_find_'
    assert 'type' in text_of(tips[0]).lower()
