"""How a rank of 214,011 fits in a list of 159,683 people.

This page exists because the dashboard used to answer that question wrongly.
It printed a researcher's rank beside the size of the published edition, as
though the two were a fraction, and they are not: `rank` is a position in a
ranking of every scientist Scopus scored, while the edition holds only the
ones who made the list. Pairing them produced statements that cannot be true,
and a reader who noticed had no way to find out why.

The shape below is the explanation, and it is a measurement rather than a
description. Every rank from 1 to 100,000 is present in all eight career
editions. Past that point coverage falls away: about half of the next 50,000,
a third of the 50,000 after that, and almost none beyond half a million. So
the list is two rules joined together. Everyone in the global top 100,000 is
in it. Beyond that, a researcher appears only if they are near the top of
their own subfield, which is why a rank far larger than the list is not a
contradiction but the normal way a specialist gets here.

Enter a rank and the page says which band it falls in and what that means,
because the general shape is only convincing once a reader can locate their
own number on it.
"""
import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from citations_lib.utils import RANK_CUTOFF, edition_years, rank_coverage

dash.register_page(__name__, path='/ranking', name='How the list is built',
                   title='How the list is built')

# Repeated from assets/style.css as hex: plotly renders to SVG and does not
# resolve CSS custom properties.
FULL = '#00B4D8'        # --ev-accent, bands that are wholly present
PARTIAL = '#F09048'     # --ev-orange, bands that are only partly present
MUTED = '#A8B2C4'       # --ev-text-muted


def _years():
    try:
        return sorted(edition_years('career'), reverse=True)
    except Exception:
        return [2024]


def _label(band):
    """A band's axis label. The first band starts at rank 1, not rank 0, and
    integer division would round it to "0-25k" and quietly claim a rank
    nobody has."""
    def thousands(value):
        return f'{value / 1000:.0f}k' if value >= 1000 else str(value)

    if band['low'] == 1:
        return f"1-{thousands(band['high'])}"
    if band['high'] >= 1_000_000:
        return f"{thousands(band['low'])}+"
    return f"{thousands(band['low'])}-{thousands(band['high'])}"


def _coverage_figure(year, highlight=None):
    data = rank_coverage('career', year)
    if not data or not data['bands']:
        return go.Figure()
    bands = data['bands']

    colours = [FULL if band['share'] > 0.999 else PARTIAL for band in bands]
    figure = go.Figure()
    figure.add_bar(
        x=[_label(b) for b in bands],
        y=[100 * b['share'] for b in bands],
        marker=dict(color=colours),
        customdata=[[b['present'], b['width']] for b in bands],
        hovertemplate=('ranks %{x}<br>%{customdata[0]:,} of %{customdata[1]:,} '
                       'are on the list<br>%{y:.2f}%<extra></extra>'),
    )

    if highlight:
        for index, band in enumerate(bands):
            if band['low'] <= highlight <= band['high']:
                figure.add_annotation(
                    x=index, y=100 * band['share'], yshift=14,
                    text=f'rank {highlight:,} is here', showarrow=True,
                    arrowhead=2, arrowcolor=MUTED,
                    font=dict(color='#E8ECF2', size=12))
                break

    figure.update_layout(
        template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)', height=380,
        margin=dict(l=50, r=20, t=50, b=50), showlegend=False,
        yaxis=dict(title='Share of that rank range on the list (%)',
                   range=[0, 108]),
        xaxis=dict(title='Overall rank among all scientists scored'),
    )
    figure.add_annotation(
        xref='paper', x=0.02, yref='y', y=104, showarrow=False,
        text=f'every rank up to {RANK_CUTOFF:,} is here',
        font=dict(color=FULL, size=11), xanchor='left')
    return figure


def _summary(year, rank=None):
    data = rank_coverage('career', year)
    if not data:
        return html.Div('No data for that edition.', className='ev-note')

    items = [
        html.Li([html.Strong(f"{data['published']:,}"),
                 ' researchers are published in this edition.']),
        html.Li([html.Strong(f"{data['highest_rank']:,}"),
                 ' is the largest rank among them, so at least that many '
                 'scientists were scored.']),
        html.Li(['Every rank up to ', html.Strong(f'{RANK_CUTOFF:,}'),
                 ' appears. Past it, a researcher is here only if they are '
                 'near the top of their own subfield.']),
    ]
    if rank:
        band = next((b for b in data['bands']
                     if b['low'] <= rank <= b['high']), None)
        if band is None:
            verdict = html.Li(
                f'Rank {rank:,} is beyond the largest rank in this edition.',
                className='ev-verdict')
        elif band['share'] > 0.999:
            verdict = html.Li(
                [f'Rank {rank:,} sits in a band that is ',
                 html.Strong('entirely'),
                 ' on the list. Every rank around it is published too.'],
                className='ev-verdict')
        else:
            verdict = html.Li(
                [f'Rank {rank:,} sits in a band where only ',
                 html.Strong(f"{100 * band['share']:.1f}%"),
                 ' of ranks appear. Someone at this rank is here on subfield '
                 'standing, not on overall position, which is why the number '
                 'can exceed the size of the list.'],
                className='ev-verdict')
        items.append(verdict)
    return html.Ul(items, className='ev-caveats')


layout = dbc.Container(fluid=True, children=[
    html.Br(),
    dbc.Row(dbc.Col([
        html.H3('How the list is built', className='ev-title'),
        dcc.Markdown(
            'A researcher can be ranked **214,011** in an edition holding '
            '**159,683** people. That looks impossible and is not.\n\n'
            '`rank` is a position among **every scientist Scopus scored**, '
            'not among the ones published here. The list is two rules joined: '
            'everyone in the global top 100,000, plus the top of each '
            'subfield. So a specialist can carry a rank far larger than the '
            'list and still belong on it.',
            className='ev-lede'),
    ], width=12)),
    html.Br(),
    dbc.Row([
        dbc.Col([
            html.Div([
                html.Span('Edition', className='ev-kicker'),
                dcc.Dropdown(id='ranking-year',
                             options=[{'label': str(y), 'value': y}
                                      for y in _years()],
                             value=_years()[0], clearable=False,
                             style={'width': '160px'}),
            ]),
            dcc.Graph(id='ranking-coverage',
                      config={'displayModeBar': False}),
        ], md=8),
        dbc.Col(html.Div([
            html.Div('Locate a rank', className='ev-kicker'),
            dcc.Input(id='ranking-rank', type='number', min=1, step=1,
                      placeholder='e.g. 214011', debounce=True,
                      className='ev-input'),
            html.Div(id='ranking-summary'),
        ], className='ev-panel'), md=4),
    ]),
    html.Br(),
    dbc.Row(dbc.Col(dcc.Markdown(
        'Bars in cyan are rank ranges where **every** rank is on the list. '
        'Bars in orange are ranges where only some are, and the height says '
        'how many. The decay is the signature of the subfield rule: the '
        'further down the overall ranking you go, the more exceptional you '
        'have to be within your own field to appear.',
        className='ev-caption'), width=12)),
    html.Br(),
])


@callback(Output('ranking-coverage', 'figure'),
          Output('ranking-summary', 'children'),
          Input('ranking-year', 'value'),
          Input('ranking-rank', 'value'))
def _update(year, rank):
    year = int(year) if year else _years()[0]
    rank = int(rank) if rank else None
    return _coverage_figure(year, rank), _summary(year, rank)
