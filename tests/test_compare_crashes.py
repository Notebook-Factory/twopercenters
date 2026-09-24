"""The three compare tabs must not crash on the states a reader can reach.

Each test calls the plain function behind a registered callback with the
values the browser would send, against the local Postgres. The callbacks are
declared inside the layout builders, so they are reached through the
dash_callback fixture rather than imported.
"""
import plotly.graph_objects as go
import pytest
from dash.exceptions import PreventUpdate

from citations_lib.utils import get_es_aggregate, update_yr_options

AUTHOR = 'Ioannidis, John P.A.'


def _figures_in(row):
    """The six metric figures inside the dbc.Row the figure callbacks return
    (as a one-element tuple, which Dash takes as a list of children)."""
    if isinstance(row, tuple):
        row, = row
    return [col.children[0].children.figure for col in row.children]


# ---------------------------------------------------------------------------
# 1. "No dataset selected" returns one value per output, in output order.
# ---------------------------------------------------------------------------

def _assert_no_dataset(result):
    assert len(result) == 3
    children, figure, formula = result
    assert children == "No dataset selected"
    assert isinstance(figure, go.Figure)
    assert formula == ''


def test_author_vs_author_no_dataset_matches_outputs(dash_callback):
    update = dash_callback("2author_figs_author_vs_author")
    _assert_no_dataset(update(True, '2024', True, '2024', False, False,
                              None, None))


def test_author_vs_group_no_dataset_matches_outputs(dash_callback):
    update = dash_callback("2group_figs_author_vs_group")
    _assert_no_dataset(update(None, 'sm-field', None, False, False,
                              True, '2024'))


def test_group_vs_group_no_dataset_matches_outputs(dash_callback):
    update = dash_callback("2group_figs_group_vs_group")
    _assert_no_dataset(update(True, 7, 'sm-field', None, 'cntry', None,
                              False, False))


# ---------------------------------------------------------------------------
# 2. group_vs_group offers no "All" group, because there is no data for it.
# ---------------------------------------------------------------------------

def _find(component, component_id):
    if getattr(component, 'id', None) == component_id:
        return component
    children = getattr(component, 'children', None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        found = _find(child, component_id)
        if found is not None:
            return found
    return None


def test_there_is_no_aggregate_for_all_researchers():
    # group_metrics holds only 'cntry' and 'sm-field', and institutions are
    # computed live; nothing answers for "all".
    assert get_es_aggregate('all', 'Dataset', 'career') == {}


@pytest.mark.parametrize('dropdown_id', ['group1ListDropdown_group_vs_group',
                                         'group2ListDropdown_group_vs_group'])
def test_group_vs_group_does_not_offer_all(dash_callback, dropdown_id):
    from citations_lib.group_vs_group_layout import group_vs_group_layout

    dash_callback("2group_figs_group_vs_group")   # the app is set up
    dropdown = _find(group_vs_group_layout(), dropdown_id)
    values = [option['value'] for option in dropdown.options]
    assert 'all' not in values
    assert values == ['cntry', 'sm-field', 'inst_name']


# ---------------------------------------------------------------------------
# 3. group_vs_group keeps the calendar year when the dataset is switched.
# ---------------------------------------------------------------------------

def _switch(dash_callback, career_before, index_before):
    update = dash_callback("selectYrRadio_group_vs_group.options")
    return update(not career_before, index_before,
                  update_yr_options(career_before))


def test_career_2019_becomes_single_year_2019(dash_callback):
    options, value = _switch(dash_callback, True, 2)
    assert options == update_yr_options(False)
    assert value == 1                 # singleyr index 1 is 2019


def test_single_year_2020_becomes_career_2020(dash_callback):
    options, value = _switch(dash_callback, False, 2)
    assert options == update_yr_options(True)
    assert value == 3                 # career index 3 is 2020


def test_career_2024_becomes_single_year_2024(dash_callback):
    options, value = _switch(dash_callback, True, 7)
    assert value == 6                 # singleyr index 6 is 2024, not 'singleyr 7'


def test_career_2018_falls_back_to_the_latest_single_year(dash_callback):
    # There is no single-year 2018 edition.
    options, value = _switch(dash_callback, True, 1)
    assert value == len([o for o in options if 'value' in o]) - 1


def test_first_load_keeps_the_initial_year(dash_callback):
    # On page load the kind has not changed: the options are already career.
    update = dash_callback("selectYrRadio_group_vs_group.options")
    options, value = update(True, 3, update_yr_options(True))
    assert value == 3


# ---------------------------------------------------------------------------
# 4. A group name left over from the previous group type does not crash.
# ---------------------------------------------------------------------------

def test_author_vs_group_figures_survive_a_stale_group_name(dash_callback):
    # Field -> Country while "Clinical Medicine" is still selected.
    update = dash_callback("2group_figs_author_vs_group")
    result = update(AUTHOR, 'cntry', 'Clinical Medicine', False, False,
                    True, '2024')
    assert len(result) == 3


def test_author_vs_group_figures_still_draw_a_real_group(dash_callback):
    update = dash_callback("2group_figs_author_vs_group")
    figures, c_fig, _ = update(AUTHOR, 'sm-field', 'Clinical Medicine',
                               False, False, True, '2024')
    assert isinstance(c_fig.data[0], go.Box)


def test_author_vs_group_card_survives_a_stale_group_name(dash_callback):
    update = dash_callback("Group2Title_author_vs_group")
    card1, card2 = update(True, '2024', 'cntry', 'Clinical Medicine')
    assert 'Country' in str(card1)


def test_author_vs_group_card_waits_for_a_group_name(dash_callback):
    update = dash_callback("Group2Title_author_vs_group")
    with pytest.raises(PreventUpdate):
        update(True, '2024', 'sm-field', None)


def test_group_vs_group_figures_survive_a_stale_group_name(dash_callback):
    update = dash_callback("2group_figs_group_vs_group")
    result = update(True, 7, 'cntry', 'Clinical Medicine', 'cntry', 'usa',
                    False, False)
    assert len(result) == 3


@pytest.mark.parametrize('fragment', ['Group1Title_group_vs_group',
                                      'Group2Title_group_vs_group'])
def test_group_vs_group_cards_survive_a_stale_group_name(dash_callback,
                                                         fragment):
    update = dash_callback(fragment)
    card1, card2 = update(True, 7, 'cntry', 'Clinical Medicine')
    assert 'Country' in str(card1)


@pytest.mark.parametrize('fragment', ['Group1Title_group_vs_group',
                                      'Group2Title_group_vs_group'])
def test_group_vs_group_cards_wait_for_a_group_name(dash_callback, fragment):
    update = dash_callback(fragment)
    with pytest.raises(PreventUpdate):
        update(True, 7, 'sm-field', None)


# ---------------------------------------------------------------------------
# 5. author_vs_author: one author draws one bar, labelled with its real value.
# ---------------------------------------------------------------------------

def test_one_author_draws_only_that_author(dash_callback):
    update = dash_callback("2author_figs_author_vs_author")
    figures, c_fig, _ = update(True, '2024', True, '2024', False, False,
                               AUTHOR, None)
    assert len(c_fig.data) == 1
    assert c_fig.data[0].y[0] > 0
    for fig in _figures_in(figures):
        assert len(fig.data) == 1
        assert fig.data[0].y[0] > 0


def test_two_authors_still_draw_both(dash_callback):
    update = dash_callback("2author_figs_author_vs_author")
    figures, c_fig, _ = update(True, '2024', True, '2024', False, False,
                               AUTHOR, 'Bengio, Yoshua')
    assert len(c_fig.data) == 2


@pytest.mark.parametrize('ns', [False, True])
def test_bar_labels_show_the_real_value(dash_callback, ns):
    # '%{text:.2s}' printed an h-index of 197 as "200". Counts are whole
    # numbers; the hm-index and the composite score are fractional.
    update = dash_callback("2author_figs_author_vs_author")
    figures, c_fig, _ = update(True, '2024', True, '2024', ns, False,
                               AUTHOR, None)
    templates = [fig.data[0].texttemplate for fig in _figures_in(figures)]
    templates.append(c_fig.data[0].texttemplate)
    # nc, h, hm, ncs, ncsf, ncsfl, c
    assert templates == ['%{text:,d}', '%{text:,d}', '%{text:.2f}',
                         '%{text:,d}', '%{text:,d}', '%{text:,d}',
                         '%{text:.2f}']
