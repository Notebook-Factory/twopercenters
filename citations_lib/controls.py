"""Controls that more than one page shares.

One module so that a control which means the same thing in six places also
looks and reads the same in all six, rather than being spelled out again
beside each layout that needs it.
"""

import dash_bootstrap_components as dbc
from dash import html

# What each half of the dataset toggle means, in the words the tooltip uses.
# The published data holds two records per researcher: everything they had
# accumulated up to a year, and what they did in that year alone.
CAREER_HINT = 'Career-long, up to the year selected'
SINGLE_HINT = 'That year on its own'


def kind_options(radio_id, disabled=False):
    """The two options, with the ids the icons and the tooltips hang on.

    Separate from kind_toggle because a callback replaces these options on
    the author pickers, to grey out a dataset a researcher has no record in.
    Rebuilt there from the words alone, that callback put "Career" and
    "Single year" back and left the tooltips pointing at labels that no
    longer existed.
    """
    options = [
        # dbc takes a string for a label and nothing else, so the icon
        # cannot be a span inside it. It is a mask on the label itself,
        # hung on these ids.
        {'label': '', 'value': True, 'label_id': 'kindCareer-' + radio_id},
        {'label': '', 'value': False, 'label_id': 'kindSingle-' + radio_id},
    ]
    if disabled:
        for option in options:
            option['disabled'] = True
    return options


def kind_toggle(radio_id, value=True, class_name=''):
    """The career / single-year switch, as two icons.

    It used to be the words "Career" and "Single year", which made it a
    different size from whatever it stood next to: the rules that size this
    control are keyed to its id prefix and were written for a toolbar where
    it stands alone and is meant to be large. An icon is the same size
    whatever it says.

    The icons are lucide's, drawn as CSS masks in style.css: a clock with a
    rewind arrow for the career-long record, which is everything up to the
    year selected, and a calendar for one year on its own. Each half carries
    a tooltip, because an icon on its own is a guess.

    `radio_id` is the id the callbacks already listen to; the two labels take
    ids derived from it, which is what the tooltips point at and what the
    stylesheet hangs the icons on.
    """
    career_id = 'kindCareer-' + radio_id
    single_id = 'kindSingle-' + radio_id
    return html.Div([
        dbc.RadioItems(
            id=radio_id, value=value,
            className='btn-group', inputClassName='btn-check',
            labelClassName='btn btn-outline-primary',
            labelCheckedClassName='active',
            options=kind_options(radio_id)),
        dbc.Tooltip(CAREER_HINT, target=career_id, placement='bottom'),
        dbc.Tooltip(SINGLE_HINT, target=single_id, placement='bottom'),
    ], className=('radio-group ev-kind-toggle ' + class_name).strip())
