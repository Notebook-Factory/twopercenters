"""Retraction exposure, including six years that were never recorded.

What the column means, because the name invites a wrong reading. The
publishers define it as "total cites 1996-2024 from papers (by any author)
marked as Retraction in RWDB": citations a researcher RECEIVED where the
CITING paper was later retracted. It is not a measure of their own conduct.
The database records that separately, in np_rw, and only 3 to 4% of listed
researchers have any. This column is 71 to 76% non-zero, because with
thousands of citations having at least one come from a paper that was later
withdrawn is close to unavoidable. It mostly tracks being highly cited.

That distinction is the reason the page spends as much space defining the
quantity as charting it. A figure that reads as an accusation when it is not
one does more harm than a figure nobody looks at.

The three retraction columns arrived with Mendeley version 7. career-2023 and
career-2024 carry them; career-2017 through career-2022 carry nothing at all,
because tracking began in 2024, not because nothing had been retracted. That
is 955,512 author-editions with a blank where a number should be.

This page shows the two measured years and the six estimated ones together,
and never lets them look alike. Measured values are drawn solid in the
Evidence cyan; estimates are drawn in a muted tone with a hatched fill, set
off by a dotted rule at the year tracking began, and labelled as estimates in
the legend, the hover text and the caption. The hatch matters more than the
colour: it survives greyscale printing and a screenshot, which a colour
difference alone does not. A reader who glances at the chart and takes
nothing else from the page should still come away knowing which half is
which.

The model's own score sits beside the chart rather than in a footnote. It was
trained on career-2023 and evaluated on career-2024, an edition it never saw,
where it reached ROC AUC 0.872 against 0.5 for chance. That number measures
discrimination only: whether the model ranks exposed researchers above
unexposed ones. Nothing here can validate the absolute level for years where
the truth was never recorded, and the page says so.

No torch, no relbench, nothing from rdl/ is imported here. Predictions reach
the dashboard as rows in Postgres, written offline by rdl/publish.py.
tests/test_no_torch_in_app.py holds that line.
"""
import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from citations_lib.utils import (author_options, get_es_results,
                                 prediction_run, retraction_by_edition,
                                 retraction_for_author)

dash.register_page(__name__, path='/retraction', name='Retraction exposure',
                   title='Retraction exposure')

# Plotly renders to SVG and does not resolve CSS custom properties, so these
# repeat the two palette values from assets/style.css rather than naming them.
MEASURED = '#00B4D8'        # --ev-accent, the cyan leaf
ESTIMATED = '#A8B2C4'       # --ev-text-muted
# Bar markers have no dash property, that belongs to scatter lines. A hatch
# pattern carries the same "this one is not solid ground" reading and
# survives being printed or screenshotted in greyscale.
ESTIMATED_FILL = 'rgba(168,178,196,0.30)'
TASK = 'retraction_exposed'


def _run_summary():
    run = prediction_run(TASK)
    if run is None:
        return html.Div(
            'No model run has been published yet. Train the task and run '
            '`python -m rdl.publish retraction_exposed`.',
            className='ev-note')
    auc = (run.get('metrics') or {}).get('roc_auc')
    baseline = (run.get('baseline') or {}).get('roc_auc')
    majority = (run.get('baseline') or {}).get('majority_accuracy')
    return html.Div([
        html.Div('How much weight these estimates carry', className='ev-kicker'),
        html.Div([
            html.Span(f'{auc:.3f}' if auc else '--', className='ev-metric'),
            html.Span(' ROC AUC on career-2024, an edition the model never saw',
                      className='ev-metric-label'),
        ]),
        html.Ul([
            html.Li(f'Chance is {baseline:.2f}.' if baseline else ''),
            html.Li(
                f'Always guessing the majority answer would be right '
                f'{majority:.1%} of the time, which is why accuracy is the '
                f'wrong measure here and AUC is quoted instead.'
                if majority else ''),
            html.Li('This measures discrimination, whether researchers who '
                    'were cited by a retracted paper are ranked above those '
                    'who were not. It cannot '
                    'validate the absolute level for years where nothing was '
                    'recorded, because there is nothing to check against.'),
        ], className='ev-caveats'),
    ])


def _overview_figure():
    rows = retraction_by_edition(TASK)
    if not rows:
        return go.Figure()

    measured = [r for r in rows if r['measured']]
    estimated = [r for r in rows if not r['measured']]
    figure = go.Figure()
    figure.add_bar(
        x=[r['data_year'] for r in estimated],
        y=[100 * r['share'] for r in estimated],
        name='Estimated (never recorded)',
        marker=dict(color=ESTIMATED_FILL,
                    line=dict(color=ESTIMATED, width=2),
                    pattern=dict(shape='/', fgcolor=ESTIMATED, size=6,
                                 solidity=0.25)),
        hovertemplate='%{x}: %{y:.1f}% estimated to have been cited by a retracted paper<extra></extra>',
    )
    figure.add_bar(
        x=[r['data_year'] for r in measured],
        y=[100 * r['share'] for r in measured],
        name='Measured (published)',
        marker=dict(color=MEASURED),
        hovertemplate='%{x}: %{y:.1f}% measured, cited by a retracted paper<extra></extra>',
    )
    if measured:
        boundary = min(r['data_year'] for r in measured) - 0.5
        figure.add_vline(x=boundary, line=dict(color=ESTIMATED, dash='dot'))
        figure.add_annotation(
            x=boundary, yref='paper', y=1.02, showarrow=False,
            text='retraction tracking begins', font=dict(color=ESTIMATED,
                                                         size=11))
    figure.update_layout(
        barmode='overlay', template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=40, r=20, t=40, b=40), height=360,
        legend=dict(orientation='h', y=-0.18),
        yaxis_title='Cited by at least one retracted paper (%)',
        xaxis_title=None,
    )
    return figure


layout = dbc.Container(fluid=True, children=[
    html.Br(),
    dbc.Row(dbc.Col([
        html.H3('Retraction exposure', className='ev-title'),
        dcc.Markdown(
            'The publishers define this column as **"total cites 1996-2024 '
            'from papers (by any author) marked as Retraction in RWDB"**. '
            'Read that carefully: it counts citations a researcher '
            '*received*, where the **citing** paper was later retracted.\n\n'
            'It is **not** a measure of their own conduct. It does not say '
            'they retracted anything; the database records that separately. '
            'Someone else cited them, and that someone else\'s paper was '
            'later withdrawn. With thousands of citations, having at least '
            'one is close to unavoidable, which is why **71 to 76% of listed '
            'researchers have a non-zero value**. A high count mostly tracks '
            'being highly cited.\n\n'
            'The published databases record this for **2023 and 2024 only**: '
            'tracking began with the seventh release, so the six earlier '
            'editions carry nothing at all. That is **955,512 '
            'author-editions** with a blank where a number should be. The '
            'blanks below are filled by a model trained on 2023 and tested '
            'on 2024. **They are estimates, not measurements**, and are '
            'drawn differently throughout so the two can never be mistaken '
            'for each other.',
            className='ev-lede'),
    ], width=12)),
    html.Br(),

    # The search comes first, because looking up a person is what this page is
    # for. It sat at the bottom under a second chart that looked like the one
    # above it, so picking a researcher appeared to change a chart at the top
    # that in fact never changes: that one is the whole list, this one is one
    # person. Naming both sections plainly and putting the search directly
    # above the thing it drives is the fix.
    dbc.Row(dbc.Col(html.Div([
        html.H5('One researcher', className='ev-subtitle'),
        dcc.Markdown(
            'Search by name. Add an institution to separate people who share '
            'one, for example "Zhu Jianguo Sydney".',
            className='ev-caption'),
        dcc.Dropdown(id='retraction-author', options=[], multi=False,
                     placeholder='Search researchers',
                     value='Ioannidis, John P.A.', searchable=True),
        html.Div(id='retraction-author-panel'),
    ], className='ev-panel'), width=12)),
    html.Br(),

    dbc.Row(dbc.Col(html.Div([
        html.Div('The three retraction columns, as the publishers define them',
                 className='ev-kicker'),
        html.Ul([
            html.Li([html.Code('np_rw'), ' - papers ',
                     html.Strong('by this author'),
                     ' marked as Retraction. This is the one about their own '
                     'work, and only 3 to 4% of listed researchers have any.'
                     ]),
            html.Li([html.Code('nc_to_rw'), ' - citations ',
                     html.Strong('to'),
                     ' those retracted papers of theirs. Also 3 to 4%.']),
            html.Li([html.Code('nc_rw'), ' - citations they received ',
                     html.Strong('from'),
                     ' papers, by anyone, that were later retracted. This is '
                     'the one charted here, and it is about who cited them '
                     'rather than what they wrote.']),
        ], className='ev-caveats'),
    ], className='ev-panel'), width=12)),
    html.Hr(),

    dbc.Row(dbc.Col(
        html.H5('Everyone on the list', className='ev-subtitle'), width=12)),
    dbc.Row(dbc.Col(dcc.Markdown(
        'The share of listed researchers cited by at least one retracted '
        'paper, per edition. This is the whole population and does not change '
        'when you search above.', className='ev-caption'), width=12)),
    dbc.Row([
        dbc.Col(dcc.Graph(id='retraction-overview', figure=_overview_figure(),
                          config={'displayModeBar': False}), md=8),
        dbc.Col(html.Div(_run_summary(), className='ev-panel'), md=4),
    ]),
    html.Br(),
])


@callback(Output('retraction-author', 'options'),
          Input('retraction-author', 'search_value'))
def _search(term):
    return author_options(
        get_es_results(term, ['career'], 'authfull'))


@callback(Output('retraction-author-panel', 'children'),
          Input('retraction-author', 'value'))
def _author_panel(name):
    if not name:
        return html.Div('Pick a researcher.', className='ev-note')
    rows = retraction_for_author(name, TASK)
    if not rows:
        return html.Div(f'No career record found for {name}.',
                        className='ev-note')

    figure = go.Figure()
    measured = [r for r in rows if r['measured']]
    estimated = [r for r in rows if not r['measured']]

    # A recorded fact and a likelihood are different kinds of statement, and
    # drawing both as a bar height put them on a scale that does not exist: a
    # year where retraction was simply recorded became "100%" and stood beside
    # a 74% estimate as though the two were the same measurement. Every bar
    # now says in words which it is, so its height is never read alone, and
    # the axis ticks are gone because there is no single quantity to tick.
    if estimated:
        figure.add_bar(
            x=[r['data_year'] for r in estimated],
            y=[100 * r['value'] for r in estimated],
            name='Estimated likelihood',
            text=[f"~{100 * r['value']:.0f}% likely" for r in estimated],
            textposition='outside',
            marker=dict(color=ESTIMATED_FILL,
                        line=dict(color=ESTIMATED, width=2),
                        pattern=dict(shape='/', fgcolor=ESTIMATED, size=6,
                                     solidity=0.25)),
            hovertemplate='%{x}: estimated %{y:.0f}% likely to have been '
                          'cited by a retracted paper<extra></extra>')
    if measured:
        figure.add_bar(
            x=[r['data_year'] for r in measured],
            # A short stub rather than zero, so a "none recorded" year is
            # visibly present and answered rather than looking like missing
            # data, which is the state this whole page is about.
            y=[100 if r['value'] else 7 for r in measured],
            name='Recorded in the published data',
            text=['recorded' if r['value'] else 'none recorded'
                  for r in measured],
            textposition='outside',
            marker=dict(color=MEASURED),
            customdata=['cited by a retracted paper' if r['value']
                        else 'not cited by any retracted paper'
                        for r in measured],
            hovertemplate='%{x}: %{customdata}, recorded<extra></extra>')

    figure.update_layout(
        template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)', height=300,
        margin=dict(l=40, r=20, t=30, b=40),
        legend=dict(orientation='h', y=-0.2),
        yaxis=dict(title=None, range=[0, 128], showticklabels=False,
                   showgrid=False),
        xaxis=dict(title=None, dtick=1))

    known = ', '.join(str(r['data_year']) for r in measured)
    guessed = ', '.join(str(r['data_year']) for r in estimated)
    if estimated:
        note = (f'Recorded in {known}. Estimated for {guessed}, where the '
                f'published data records nothing.')
    else:
        # Not a gap in the estimates: this researcher has no rows at all in
        # the untracked editions, so there is nothing to estimate. "Estimated
        # for none" made that read as a failure of the model.
        note = (f'Recorded in {known}. This researcher does not appear in the '
                f'2017-2022 editions, so there is nothing to estimate for '
                f'them.')
    return html.Div([
        dcc.Graph(figure=figure, config={'displayModeBar': False}),
        dcc.Markdown(f'**{name}**. {note}', className='ev-caption'),
    ])
