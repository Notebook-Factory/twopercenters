"""Retraction exposure, including six years that were never recorded.

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
where it reached ROC AUC 0.872 against 0.5 for chance. That number is the
honest measure of how much weight these estimates carry, and it measures
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
            html.Li('This measures discrimination, whether exposed '
                    'researchers are ranked above unexposed ones. It cannot '
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
        hovertemplate='%{x}: %{y:.1f}% estimated exposed<extra></extra>',
    )
    figure.add_bar(
        x=[r['data_year'] for r in measured],
        y=[100 * r['share'] for r in measured],
        name='Measured (published)',
        marker=dict(color=MEASURED),
        hovertemplate='%{x}: %{y:.1f}% measured exposed<extra></extra>',
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
        yaxis_title='Researchers with any exposure (%)', xaxis_title=None,
    )
    return figure


layout = dbc.Container(fluid=True, children=[
    html.Br(),
    dbc.Row(dbc.Col([
        html.H3('Retraction exposure', className='ev-title'),
        dcc.Markdown(
            'Whether a researcher has received citations from work that was '
            'later retracted. The published databases record this for **2023 '
            'and 2024 only**: tracking began with the seventh release, so the '
            'six earlier editions carry nothing at all. That is **955,512 '
            'author-editions** with a blank where a number should be.\n\n'
            'The blanks below are filled by a model trained on 2023 and '
            'tested on 2024. **They are estimates, not measurements**, and '
            'are drawn differently throughout so the two can never be '
            'mistaken for each other.',
            className='ev-lede'),
    ], width=12)),
    html.Br(),
    dbc.Row([
        dbc.Col(dcc.Graph(id='retraction-overview', figure=_overview_figure(),
                          config={'displayModeBar': False}), md=8),
        dbc.Col(html.Div(_run_summary(), className='ev-panel'), md=4),
    ]),
    html.Hr(),
    dbc.Row(dbc.Col([
        html.H5('One researcher', className='ev-subtitle'),
        dcc.Markdown(
            'Search by name, or add an institution to separate people who '
            'share one: "Zhu Jianguo Sydney".', className='ev-hint'),
        dcc.Dropdown(id='retraction-author', options=[], multi=False,
                     placeholder='Search researchers',
                     value='Ioannidis, John P.A.', searchable=True),
        html.Br(),
        html.Div(id='retraction-author-panel'),
    ], width=12)),
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
    if estimated:
        figure.add_bar(
            x=[r['data_year'] for r in estimated],
            y=[100 * r['value'] for r in estimated],
            name='Estimated likelihood of exposure',
            marker=dict(color=ESTIMATED_FILL,
                        line=dict(color=ESTIMATED, width=2),
                        pattern=dict(shape='/', fgcolor=ESTIMATED, size=6,
                                     solidity=0.25)),
            hovertemplate='%{x}: %{y:.0f}% estimated likelihood'
                          '<extra></extra>')
    if measured:
        figure.add_bar(
            x=[r['data_year'] for r in measured],
            y=[100 if r['value'] else 0 for r in measured],
            name='Measured: exposure recorded',
            marker=dict(color=MEASURED),
            hovertemplate='%{x}: %{customdata}<extra></extra>',
            customdata=['exposure recorded' if r['value'] else 'none recorded'
                        for r in measured])
    figure.update_layout(
        template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)', height=300,
        margin=dict(l=40, r=20, t=30, b=40),
        legend=dict(orientation='h', y=-0.2),
        yaxis=dict(title='%', range=[0, 105]), xaxis_title=None)

    known = ', '.join(str(r['data_year']) for r in measured) or 'none'
    guessed = ', '.join(str(r['data_year']) for r in estimated) or 'none'
    return html.Div([
        dcc.Graph(figure=figure, config={'displayModeBar': False}),
        dcc.Markdown(
            f'**{name}**. Measured in {known}. Estimated for {guessed}, '
            f'where the published data records nothing.',
            className='ev-hint'),
    ])
