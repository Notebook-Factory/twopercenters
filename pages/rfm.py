"""What the relational model is, and what it was allowed to fill in.

Six career editions, 2017 through 2022, carry no retraction data at all. The
columns arrived with Mendeley version 7, so 955,512 rows are blank because
nothing was tracked, not because nothing was retracted. The retraction page
shows those estimates. This page says where they came from.

The short version is that the database is already a graph. Every foreign key
is an edge, so a career row reaches its author, that author's other years,
the institution, the country, the field and the two subfields without anyone
writing a join. A relational model walks that neighbourhood and predicts a
column from it, which is why one model answers questions that would each
need their own feature table otherwise.

Two things on this page are there to keep it honest. The scoreboard shows
every task that was trained, not only the two that shipped, and each score
sits beside the trivial baseline for the same split: on the forecasting
tasks the trivial baseline wins outright, so nothing from them is published.
And the model here is a graph network trained locally with RelBench, not
KumoRFM itself, because the hosted endpoint cannot currently be reached
(docs/kumo-access-ask.md).
"""
import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html

from citations_lib.utils import (graph_table_sizes, prediction_coverage,
                                 prediction_run)

dash.register_page(__name__, path='/predictions', name='RFM predictions',
                   title='RFM predictions')

# Repeated from assets/style.css as hex: plotly renders to SVG and does not
# resolve CSS custom properties.
ACCENT = '#00B4D8'
MUTED = '#A8B2C4'
ORANGE = '#F09048'
EDGE = '#4A5670'
# See pages/retraction.py: plotly takes a hover label's background from the
# trace's marker colour, which makes a pale marker's tooltip unreadable.
HOVER = dict(bgcolor='#303C54', bordercolor='#4A5670',
             font=dict(color='#E8ECF2', size=12))

# Where each table sits in the picture. Laid out by hand rather than by a
# spring algorithm: the schema has seven tables and one obvious hub, and a
# fixed layout means the same diagram every time someone loads the page.
NODES = {
    'career_metrics': (0.0, 0.0),
    'authors': (-2.3, 0.95),
    'editions': (-2.3, -0.95),
    'institutions': (2.1, 1.25),
    'countries': (3.5, 0.35),
    'fields': (2.1, -1.25),
    'subfields': (3.5, -0.45),
}

# One entry per foreign key relation, with how many keys it carries.
# career_metrics reaches subfields twice, through subfield_1_id and
# subfield_2_id, because a researcher is placed in a primary and a secondary
# subfield and both are real edges.
EDGES = [
    ('career_metrics', 'authors', 'author_id'),
    ('career_metrics', 'editions', 'edition_id'),
    ('career_metrics', 'institutions', 'institution_id'),
    ('career_metrics', 'fields', 'field_id'),
    ('career_metrics', 'subfields', 'subfield_1_id, subfield_2_id'),
    ('career_metrics', 'countries', 'country_code'),
    ('institutions', 'countries', 'country_code'),
    ('subfields', 'fields', 'field_id'),
]

WHAT_EACH_TABLE_IS = {
    'career_metrics': 'one researcher in one edition: rank, citations, '
                      'h-index, and the retraction columns',
    'authors': 'a resolved identity, held together across editions',
    'editions': 'one published table, with its data year',
    'institutions': 'the affiliation printed on the row',
    'countries': 'the country of that affiliation',
    'fields': 'the 22 top-level fields of the Scopus taxonomy',
    'subfields': 'the 177 subfields, each nested under a field',
}

# Every task that was trained, with the score it got on data it never saw
# and the trivial baseline for the same split. The two retraction tasks read
# their numbers from the database, since those are published runs. The other
# three were trained and then not published, so their numbers are recorded
# here from rdl/train.py and docs/identity-resolution-findings.md.
UNPUBLISHED = [
    dict(task='dropout', metric='ROC AUC', higher_is_better=True,
         model=0.687, baseline=0.506,
         baseline_label='the is_ambiguous flag alone',
         note='Beats its baseline, but only after the identity repair. '
              'Before it the model scored 0.814 and the flag scored 0.776, '
              'so most of that number was the model detecting our own '
              'resolver failing.'),
    dict(task='next_rank', metric='nMAE', higher_is_better=False,
         model=0.295, baseline=0.079,
         baseline_label="repeating last year's rank",
         note='Repeating last year is nearly four times more accurate. '
              'Nothing here is published.'),
    dict(task='next_score', metric='nMAE', higher_is_better=False,
         model=0.299, baseline=0.054,
         baseline_label="repeating last year's composite score",
         note='Same result, more starkly. Nothing here is published.'),
]


def _safe(fn, *args, default=None):
    try:
        return fn(*args)
    except Exception:
        return default


def _schema_figure():
    sizes = _safe(graph_table_sizes, default={}) or {}
    figure = go.Figure()

    for source, target, keys in EDGES:
        x0, y0 = NODES[source]
        x1, y1 = NODES[target]
        figure.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1], mode='lines',
            line=dict(color=EDGE, width=2.4 if ', ' in keys else 1.4),
            hoverinfo='skip', showlegend=False))
        figure.add_trace(go.Scatter(
            x=[(x0 + x1) / 2], y=[(y0 + y1) / 2], mode='markers',
            marker=dict(size=14, color='rgba(0,0,0,0)'),
            hovertemplate=f'{source} &#8594; {target}<br>{keys}<extra></extra>',
            showlegend=False))

    # Node area tracks row count on a log scale. Linear would draw countries
    # (203 rows) as a dot next to a career_metrics blob, which says nothing
    # a reader can use.
    def radius(name):
        rows = sizes.get(name, 0)
        if rows <= 0:
            return 26
        import math
        return 16 + 7 * math.log10(rows)

    names = list(NODES)
    figure.add_trace(go.Scatter(
        x=[NODES[n][0] for n in names], y=[NODES[n][1] for n in names],
        mode='markers+text',
        marker=dict(size=[radius(n) for n in names],
                    color=[ACCENT if n == 'career_metrics' else '#2C3A52'
                           for n in names],
                    line=dict(color=ACCENT, width=1.6)),
        text=names, textposition='bottom center',
        textfont=dict(color='#E8ECF2', size=12),
        customdata=[[f"{sizes.get(n, 0):,}", WHAT_EACH_TABLE_IS[n]]
                    for n in names],
        hovertemplate=('<b>%{text}</b><br>%{customdata[0]} rows'
                       '<br>%{customdata[1]}<extra></extra>'),
        showlegend=False))

    figure.update_layout(
        template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)', height=420,
        margin=dict(l=20, r=20, t=20, b=30), hoverlabel=HOVER,
        xaxis=dict(visible=False, range=[-3.4, 4.6]),
        yaxis=dict(visible=False, range=[-2.1, 2.1], scaleanchor='x'))
    return figure


def _rows_for_scoreboard():
    rows = []
    exposed = _safe(prediction_run, 'retraction_exposed')
    if exposed:
        rows.append(dict(
            task='retraction_exposed', metric='ROC AUC',
            higher_is_better=True,
            model=float(exposed['metrics']['roc_auc']),
            baseline=float(exposed['baseline']['roc_auc']),
            published=True))
    exposure = _safe(prediction_run, 'retraction_exposure')
    if exposure:
        rows.append(dict(
            task='retraction_exposure', metric='nMAE',
            higher_is_better=False,
            model=float(exposure['metrics']['nmae']),
            baseline=float(exposure['baseline']['median_nmae']),
            published=True))
    rows.extend(dict(published=False, **{k: v for k, v in item.items()
                                         if k not in ('note',
                                                      'baseline_label')})
                for item in UNPUBLISHED)
    return rows


def _scoreboard_figure():
    rows = _rows_for_scoreboard()
    if not rows:
        return go.Figure()
    rows = list(reversed(rows))   # plotly draws the first row at the bottom

    labels = [f"{r['task']}<br><span style='font-size:11px'>{r['metric']}, "
              f"{'higher' if r['higher_is_better'] else 'lower'} is better"
              f"</span>" for r in rows]
    beats = [(r['model'] > r['baseline']) if r['higher_is_better']
             else (r['model'] < r['baseline']) for r in rows]

    figure = go.Figure()
    figure.add_bar(
        y=labels, x=[r['baseline'] for r in rows], orientation='h',
        name='trivial baseline', marker=dict(color=MUTED),
        offsetgroup='baseline',
        hovertemplate='trivial baseline: %{x:.3f}<extra></extra>')
    figure.add_bar(
        y=labels, x=[r['model'] for r in rows], orientation='h',
        marker=dict(color=[ACCENT if b else ORANGE for b in beats]),
        hovertemplate='the model: %{x:.3f}<extra></extra>',
        offsetgroup='model', showlegend=False)
    # The model's bars are two colours, and a legend entry can only carry
    # one. Plotly would show whichever it likes, which here was orange
    # against four cyan bars. These two never draw anything: they exist so
    # the key says which colour means what.
    for colour, caption in ((ACCENT, 'the model, beating its baseline'),
                            (ORANGE, 'the model, losing to its baseline')):
        figure.add_bar(y=[labels[0]], x=[None], orientation='h',
                       name=caption, marker=dict(color=colour),
                       offsetgroup='model', hoverinfo='skip')
    figure.update_layout(
        template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)', height=420, barmode='group',
        bargap=0.35, margin=dict(l=170, r=30, t=40, b=40),
        hoverlabel=HOVER, hovermode='y unified',
        legend=dict(orientation='h', y=1.12, x=0),
        xaxis=dict(title='metric value', gridcolor='#2C3A52',
                   zeroline=False),
        yaxis=dict(title=None))
    return figure


def _coverage_panel():
    coverage = _safe(prediction_coverage, 'retraction_exposed')
    if not coverage:
        return html.Div('No published run yet.', className='ev-note')
    return html.Div([
        html.Div('What it produced', className='ev-kicker'),
        html.Div([html.Span(f"{coverage['rows']:,}", className='ev-metric'),
                  html.Span('estimates', className='ev-metric-label')]),
        html.Ul([
            html.Li([html.Strong(f"{coverage['authors']:,}"),
                     ' researchers, across ',
                     html.Strong(f"{coverage['editions']}"),
                     f" editions ({coverage['first_year']}"
                     f"-{coverage['last_year']})."]),
            html.Li('Every one is stored in its own table, never as a column '
                    'on a published figure, and every one carries the run it '
                    'came from and that run\'s score.'),
            html.Li(['They are shown on the ',
                     dcc.Link('retraction exposure', href='/retraction'),
                     ' page, always labelled estimated.']),
        ], className='ev-caveats'),
    ], className='ev-panel')


def _unpublished_list():
    return html.Ul([
        html.Li([html.Strong(item['task']), ': ',
                 f"{item['metric']} {item['model']:.3f} against "
                 f"{item['baseline']:.3f} for {item['baseline_label']}. ",
                 item['note']])
        for item in UNPUBLISHED
    ], className='ev-caveats')


layout = dbc.Container(fluid=True, children=[
    html.Br(),
    dbc.Row(dbc.Col([
        html.H3('Predictions from the relational model', className='ev-title'),
        dcc.Markdown(
            'Six editions of this list, **2017 through 2022**, carry no '
            'retraction data at all. Those columns only arrived with '
            'Mendeley version 7, so the rows are blank because nothing was '
            'tracked, not because nothing was retracted.\n\n'
            'A relational model fills that gap. It does not read a flat '
            'table of hand-built features: it reads the database as it is, '
            'treating every foreign key as an edge, and learns from the '
            'neighbourhood each row sits in. That neighbourhood is the '
            "researcher's other years, the institution, the country, the "
            'field and the subfields, all reachable without writing a '
            'single join.',
            className='ev-lede'),
    ], width=12)),
    html.Br(),
    dbc.Row([
        dbc.Col([
            html.Div('The graph it reads', className='ev-kicker'),
            dcc.Graph(figure=_schema_figure(),
                      config={'displayModeBar': False}),
            dcc.Markdown(
                'Seven tables, eight foreign-key relations. Circle area is '
                'the row count on a log scale, and `career_metrics` is the '
                'hub because every other table hangs off it. Hover a table '
                'for what it holds, or a line for the key that joins it. '
                'Names are deliberately absent from the graph: they are '
                'nearly row-unique, and embedding them would let name origin '
                'act as a proxy on a list that ranks people.',
                className='ev-caption'),
        ], md=7),
        dbc.Col(_coverage_panel(), md=5),
    ]),
    html.Br(),
    html.Hr(),
    dbc.Row(dbc.Col([
        html.H4('Every task that was trained', className='ev-subtitle'),
        dcc.Markdown(
            'A score means nothing on its own, so each bar sits beside the '
            'dumbest thing that could have been done instead: guessing, '
            'predicting the median, or repeating last year. Cyan beats its '
            'baseline. Orange loses to it.',
            className='ev-caption'),
        dcc.Graph(figure=_scoreboard_figure(),
                  config={'displayModeBar': False}),
    ], width=12)),
    dbc.Row(dbc.Col([
        html.Div('Why only two of the five are published',
                 className='ev-kicker'),
        _unpublished_list(),
    ], width=12)),
    html.Br(),
    html.Hr(),
    dbc.Row(dbc.Col(dcc.Markdown(
        '**One note on the name.** KumoRFM is the relational foundation '
        'model this work was planned around, and it is not what produced '
        'these numbers: its hosted endpoint now redirects to NVIDIA '
        'documentation and cannot be authenticated against, so the model '
        'here is a graph network trained locally with RelBench on the same '
        'schema. The database was exported for either one, so if access '
        'opens up the comparison is a run away, not a rebuild.',
        className='ev-caption'), width=12)),
    html.Br(),
])
