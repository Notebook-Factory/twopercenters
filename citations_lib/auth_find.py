
# ==========================================================================================
# ==========================================================================================
# IMPORT LIBRARIES
# ==========================================================================================
# ==========================================================================================

# =============== misc libs & modules
import numpy as np
import math
import pickle
import json
from sys import getsizeof
# =============== Plotly libs & modules
import plotly.graph_objects as go
import country_converter as coco


# =============== Plotly Dash libraries
import dash
from dash import html, dcc, callback, ctx #, Input, Output
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq

# =============== Custom lib
from citations_lib.create_fig_helper_functions import *
from citations_lib.utils import *
from citations_lib.callback_templates import *
import dash_loading_spinners as dls
# The gauge outline has to read on BOTH pages. Charts here are drawn once and
# set transparent (bgc), so the page background shows through and a theme
# switch never redraws them; a colour picked for one theme is therefore stuck
# on the other. Plotly's default gauge border is #444, which is clear on the
# light ground (#F4F6FA) and all but invisible on the dark one (#394459),
# which is why the dark gauges looked unfinished.
#
# #7E8AA0 sits between the two grounds in luminance, so it separates from
# each. bgcolor is transparent for the same reason as bgc: the arc's interior
# should be whatever the page is.
GAUGE_EDGE = '#7E8AA0'

# The what-if calculator.
#
# The composite score is not a black box: it is the sum of six log ratios,
# and citations_lib.utils.composite_score reproduces every published value
# exactly. So a reader can move any of the six indicators and be told,
# without a model and without a guess, where that score would have landed in
# the same edition.
#
# Everything the calculator draws is magenta, and everything published is
# cyan, on every gauge and on the rank at once. A reader who looks away and
# back has to be able to tell in one glance whether the number in front of
# them is the researcher's or their own invention.
#
# Magenta rather than orange: the orange line across each gauge already means
# the group median, and a what-if bar in the same colour would sit right on
# top of the thing it has to be told apart from.
GAUGE_BAR = '#00B4D8'
WHATIF_BAR = '#D86CB4'

# The six indicators, in the order the gauges are drawn, with the short label
# that goes under each input box.
WHATIF_METRICS = (
    ('nc', 'Citations'),
    ('h', 'H-index'),
    ('hm', 'Hm-index'),
    ('ncs', 'Cites, single-authored'),
    ('ncsf', 'Cites, single + first'),
    ('ncsfl', 'Cites, single + first + last'),
)


# The heading over each gauge, in the order they are drawn. Module level
# because the what-if callback redraws them without going near the function
# that built them the first time.
GAUGE_TITLES = (
    'Number of citations',
    'H-index',
    'Hm-index',
    'Number of citations to single<br> authored papers',
    'Number of citations to single<br> and first authored papers',
    'Number of citations to single,<br> first and last authored papers',
    'Composite score',
)


def gauge_figure(title, value, max_metric, whatif=False, reference=None):
    """One indicator gauge, published or hypothetical.

    max_metric is [median, ceiling] for the selected group: the median is the
    line across the arc, the ceiling is the top of the axis. A what-if value
    can exceed the ceiling, so the axis grows to fit rather than pegging the
    needle and quietly lying about the size of the change.

    `reference` is what the delta underneath counts from. For a published
    gauge that is the group median, which is the comparison the page has
    always made. In what-if mode it becomes the researcher's real value, so
    the delta reads as the size of the change the reader just made.
    """
    median, ceiling = max_metric[0], max_metric[1]
    if reference is None:
        reference = median
    try:
        ceiling = max(ceiling, value * 1.05)
    except TypeError:
        pass

    fig = make_subplots(rows=1, cols=1, specs=[[{'type': 'indicator'}]])
    fig.add_trace(go.Indicator(
        mode='gauge+number+delta', value=value,
        delta={'reference': reference,
               'increasing': {'color': '#84B460'},
               'decreasing': {'color': '#D86CB4'}},
        gauge={'threshold': {'line': {'color': '#F09048', 'width': 3},
                             'thickness': 0.75, 'value': median},
               'axis': {'tickmode': 'auto', 'range': [None, ceiling],
                        'tickwidth': 1, 'tickcolor': '#A8B2C4'},
               'bar': {'color': WHATIF_BAR if whatif else GAUGE_BAR},
               # Bar and outline together, because those are the only two
               # parts of a gauge the page's theme rules leave alone. The
               # title and the big number are restyled by assets/style.css
               # to follow the theme (.gtitle and .number), deliberately and
               # for their own good reasons, so a colour set on either here
               # would never reach the browser.
               'bordercolor': WHATIF_BAR if whatif else GAUGE_EDGE,
               'borderwidth': 2 if whatif else 1,
               'bgcolor': 'rgba(0,0,0,0)'}),
        row=1, col=1)
    fig.update_layout(
        height=200, title_x=0.5, title_y=0.85,
        title={'text': title, 'font': {'size': 14, 'color': '#E8ECF2'}},
        font={'size': 12, 'color': '#A8B2C4'},
        plot_bgcolor=bgc, paper_bgcolor=bgc,
        margin={'l': 10, 'r': 5, 'b': 10, 't': 100}, showlegend=False)
    fig.update_xaxes(automargin=True, showgrid=True, gridcolor=darkAccent2,
                     linecolor=darkAccent2, tickmode='array', tickvals=[])
    return fig


def bullet_rows(values, maxima, quartiles):
    """One row per indicator for the bullet chart in the author card.

    The six gauges this replaces each had their own axis -- 250k for
    citations, 200 for the h-index, 80 for hm -- so nothing could be compared
    across them and the group median landed as a 3px tick near zero on the
    wide ones.

    Every row here is that indicator's own term in the composite score,
    ln(v+1)/ln(max+1), which is between 0 and 1 for all six and sums to the
    published score. So one axis serves all of them, the median sits where it
    can be seen, and the parts visibly add up to the number the formula under
    the card produces.
    """
    rows = []
    for metric, label in WHATIF_METRICS:
        ceiling = maxima.get(metric)
        value = values.get(metric)
        if not ceiling or value is None:
            continue

        def share(x):
            return math.log(max(float(x), 0.0) + 1) / math.log(ceiling + 1)

        quarters = quartiles.get(metric) or {}
        rows.append({
            'key': metric,
            'label': label,
            'value': float(value),
            'share': round(share(value), 4),
            'q1': round(share(quarters.get('q1') or 0), 4),
            'median': round(share(quarters.get('median') or 0), 4),
            'q3': round(share(quarters.get('q3') or 0), 4),
            'median_raw': quarters.get('median'),
        })
    return rows


def bullet_payload(rows, group_label, whatif=False, published=None):
    """What the clientside bullet chart draws.

    `published` is the untouched set of rows, carried only in what-if mode so
    each bar can show where the real value sat before the reader moved it.
    """
    return {'rows': rows, 'group': str(group_label or ''),
            'whatif': bool(whatif),
            'published': published if whatif else None}


def gauge_legend(group_label):
    """What the gauges are measured against, in words and in colour.

    Two things on every gauge came from the same choice and neither was
    labelled: the top of the arc is the highest value in the selected group,
    and the line across it is that group's median. The control that picks the
    group used to carry the explanation in its own option text, where it said
    the line was red. It is orange.
    """
    if not group_label:
        return []
    return [
        html.Span([html.Span(className='ev-legend-line'),
                   html.Span('median in '), html.Strong(str(group_label))],
                  className='ev-legend-item'),
        html.Span([html.Span(className='ev-legend-cap'),
                   html.Span('gauge maximum: the highest in '),
                   html.Strong(str(group_label))],
                  className='ev-legend-item'),
    ]


def card_header(name, institute, country, field, edition=None):
    """Who this is, above the numbers, and which edition it is drawn from.

    The edition belongs here rather than under the numbers: every figure on
    the card is that edition's, and a reader who misses which year they are
    looking at misreads all of them.
    """
    def meta(icon, text):
        if not text or str(text).lower() in ('nan', 'none'):
            return None
        return html.Span([html.Span(className=f'ev-ic ev-ic-{icon}'),
                          html.Span(str(text))],
                         className='ev-id-meta-item')

    items = [meta('building-2', institute), meta('map-pin', country),
             meta('microscope', field)]
    left = html.Div([
        html.Div(name or 'No author selected', className='ev-id-name'),
        html.Div([i for i in items if i], className='ev-id-meta'),
    ])
    if not edition:
        return [left]
    return [left, html.Div([html.Span(className='ev-ic ev-ic-calendar'),
                            html.Span(edition)], className='ev-id-edition')]


def rank_stats(scopus_rank, list_rank, published, whatif=False, was=None):
    """The two ranks, side by side, with what each one counts.

    These used to be one number. `rank` is a position among every scientist
    Scopus scored, so on a list of 230,333 people it runs past a million, and
    printing it beside the size of the list produced statements that cannot
    be true. The position on the list is the number a reader assumed they
    were being shown, and it is the one that moves sensibly, so both are here
    and each is labelled with what it counts.
    """
    colour = WHATIF_BAR if whatif else GAUGE_BAR

    def cell(value, label, detail):
        return html.Div([
            html.Div(f'{value:,}' if isinstance(value, int) else '-',
                     className='ev-rank-value', style={'color': colour}),
            html.Div(label, className='ev-rank-label'),
            html.Div(detail, className='ev-rank-detail'),
        ], className='ev-rank-cell')

    cells = [
        cell(list_rank, 'on this list',
             f'of {published:,} published' if published else ''),
        cell(scopus_rank, 'Scopus rank', 'among everyone scored'),
    ]
    if whatif:
        cells.insert(0, html.Div([html.Span(className='ev-ic ev-ic-flask-conical'),
                                  html.Span('what if')],
                                 className='ev-id-badge'))
    children = [html.Div(cells, className='ev-rank-row')]
    if whatif and was:
        children.append(html.Div(
            [html.Span('published: '),
             html.Strong(f"{was['list_rank']:,}"), html.Span(' on this list, '),
             html.Strong(f"{was['scopus_rank']:,}"), html.Span(' Scopus')],
            className='ev-rank-was'))
    return children


def card_chips(self_pct, subfield_standing):
    """The two facts that are neither identity nor rank.

    Self-citation is a share, so it gets a bar rather than a number on its
    own: 10.59% means nothing to a reader who has not seen the others.
    """
    chips = []
    if self_pct is not None:
        share = max(0.0, min(float(self_pct), 100.0))
        chips.append(html.Div([
            html.Div([html.Span(className='ev-ic ev-ic-quote'),
                      html.Span('Self-citations'),
                      html.Strong(f'{share:.2f}%')], className='ev-chip-head'),
            html.Div(html.Div(className='ev-chip-fill',
                              style={'width': f'{share:.2f}%'}),
                     className='ev-chip-track'),
        ], className='ev-chip'))
    if subfield_standing:
        chips.append(html.Div([
            html.Div([html.Span(className='ev-ic ev-ic-target'),
                      html.Span('Subfield standing')], className='ev-chip-head'),
            html.Div(subfield_standing, className='ev-chip-body'),
        ], className='ev-chip'))
    return chips


def share_row(suffix):
    """Three ways to take the card somewhere else.

    The image is drawn from the figures rather than captured off the screen,
    so what gets shared cannot quietly disagree with what is on the page, and
    it always carries the published numbers: a what-if is an invention and
    has no business leaving the site looking like a record.
    """
    def button(name, icon, label):
        return html.Button(
            [html.Span(className=f'ev-ic ev-ic-{icon}'), html.Span(label)],
            id=name + suffix, n_clicks=0, className='ev-share-btn')

    return html.Div([
        button('shareX', 'share-2', 'Post on X'),
        button('shareImage', 'download', 'Download card'),
        button('shareCopy', 'clipboard-copy', 'Copy image'),
        html.Span(id='shareStatus' + suffix, className='ev-share-status'),
    ], className='ev-share-row')


def share_payload(name, institute, country, field, edition, standing,
                  self_pct, subfield_text):
    """Everything the share image prints. Published figures only."""
    if not standing:
        return None
    return {
        'name': name or '',
        'institute': str(institute or ''),
        'country': str(country or ''),
        'field': str(field or ''),
        'edition': edition or '',
        'list_rank': standing.get('within_list'),
        'scopus_rank': standing.get('scopus_rank'),
        'published': standing.get('published'),
        'self_pct': self_pct,
        'subfield': subfield_text or '',
    }


def rank_chart_payload(list_rank, scopus_rank, published, whatif=False):
    """What the clientside ECharts callback needs to draw the rank strip.

    The strip is the one picture that shows the whole point of the two
    numbers: the list runs from 1 to `published`, and a Scopus rank can sit
    far outside it. On a linear axis a rank of 60 and a rank of 908,824 put
    the interesting marker on the very edge, so the axis is logarithmic.
    """
    if not list_rank or not published:
        return None
    return {'list_rank': int(list_rank),
            'scopus_rank': int(scopus_rank) if scopus_rank else int(list_rank),
            'published': int(published),
            'whatif': bool(whatif)}


# BEGIN: RUN ONLY ON DATA CHANGE ------------------------------------------------
"""
The following is to avoid es queries to retrive information re 
the whole entries. By default the max size is 10k. Using scroll, pagination,
token etc., it is possible to retrieve the whole data, yet often pointless. 
It defeats the purpose of using ES. Just for consistency, following will use 
indexes instead of pd dataframes to export author list, c-scores list and 
the number of records etc. 
"""
# query = { "query": { "match_all": {} }, "_source": ['authfull'] }
page_size = 8000

# info_all  = {}
# all_auth_career = []
# all_auth_singleyr = []
# for total_pages, page_counter, page_items, page_data in es_scroll('career', query, page_size=page_size):
#     all_auth_career.append(page_data['hits']['hits'])
# for total_pages, page_counter, page_items, page_data in es_scroll('singleyr', query, page_size=page_size):
#     all_auth_singleyr.append(page_data['hits']['hits'])

# career_all = [d['_source']['authfull']
#                     for tmp in all_auth_career
#                     for d in tmp]
# singleyr_all = [d['_source']['authfull']
#                     for tmp in all_auth_singleyr
#                     for d in tmp]

# info_all['career'] = {}
# info_all['career']['total'] = len(career_all)
# info_all['singleyr'] = {}
# info_all['singleyr']['total'] = len(singleyr_all)
# all_authors = set(career_all + singleyr_all)
# info_all['total'] = len(all_authors)

# # Write it all 
# write_pickle(all_authors,'all_auth_names.pickle')
# # Write summary 
# write_json(info_all,"cumulative_summary.json")

# query = { "query": { "match_all": {} }, "_source": ['data'] }
# page_size = 8000

# career_data = []
# singleyr_data = []
# for total_pages, page_counter, page_items, page_data in es_scroll('career', query, page_size=page_size):
#      career_data.append(page_data['hits']['hits'])

# This is a bit tricky...F
# for tmp in career_data:
#     for d in tmp:
#         aa = base64_decode_and_decompress(d['_source']['data'],False)
#         print(aa)
#         break

# career_all_c = [base64_decode_and_decompress(d['_source']['data'])
#                     for tmp in career_data
#                     for d in tmp]
#write_pickle(career_all_c,'career_c.pickle')

# for total_pages, page_counter, page_items, page_data in es_scroll('singleyr', query, page_size=page_size):
#      singleyr_data.append(page_data['hits']['hits'])


# COUNTRY DATA AGG

# query = { "query": { "match_all": {} }, "_source": ['cntry','data'] }

# career_data = []
# for total_pages, page_counter, page_items, page_data in es_scroll('career_cntry', query, page_size=page_size):
#      career_data.append(page_data['hits']['hits'])
# career_all_c = [{'ct': d['_source']['cntry'],'dat': base64_decode_and_decompress(d['_source']['data'],False)}
#                     for tmp in career_data
#                     for d in tmp]
# write_pickle(career_all_c,'cntry_career.pkl')

# singleyr_data = []
# for total_pages, page_counter, page_items, page_data in es_scroll('singleyr_cntry', query, page_size=page_size):
#      singleyr_data.append(page_data['hits']['hits'])
# singleyr_all_c = [{'ct': d['_source']['cntry'],'dat': base64_decode_and_decompress(d['_source']['data'],False)}
#                     for tmp in singleyr_data
#                     for d in tmp]
# write_pickle(singleyr_all_c,'cntry_singleyr.pkl')


# END: RUN ONLY ON DATA CHANGE ------------------------------------------------


def author_find_layout(default_author='Ioannidis, John P.A.'):
    """The "Find an author" tab.

    default_author lets the spotlight search open this tab on the name the
    user just picked. The tab's content is built on demand by home.py's
    switch_tab callback, so the dropdown does not exist until the tab is
    shown; seeding it at build time is what makes the hand-off work without
    a callback writing into a component that may not be mounted.
    """

    # ========================================================================================== 
    # ========================================================================================== 
    # Data Preparation
    # ========================================================================================== 
    # ========================================================================================== 

    #dfs_career, dfs_singleyr, dfs_career_log, dfs_singleyr_log, _, _, _, _ = load_standardized_data()
    # vert_slider_length = 500
    # dropdown_opts = dict()
    # for i in range(5):
    #     with open(f'data/aggregate_info/info_career_{i}.pkl', 'rb') as fp: info = pickle.load(fp)
    #     dropdown_opts['career ' + str(i)] = info
    # for i in range(4):
    #     with open(f'data/aggregate_info/info_singleyr_{i}.pkl', 'rb') as fp: info = pickle.load(fp)
    #     dropdown_opts['singleyr ' + str(i)] = info

    # ========================================================================================== 
    # ========================================================================================== 
    # Color formatting
    # ========================================================================================== 
    # ========================================================================================== 
    darkAccent1 = '#394459' # navy ground (Evidence)
    darkAccent2 = '#4A5670' # raised surface
    darkAccent3 = '#E8ECF2' # near-white text
    lightAccent1 = '#00B4D8' # cyan leaf, primary accent
    highlight1 = '#84B460' # green leaf
    highlight2 = '#D86CB4' # magenta leaf

    g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
    g2c = [highlight2, darkAccent3] # bar plot bar 3
    # Transparent, not a colour: the page's own background shows through,
    # so a chart follows the light/dark switch without being redrawn.
    bgc = 'rgba(0,0,0,0)' # chart background: inherit the page
    SUFFIX = '_author_find_'

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 1: select dataset!
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Select dataset!

    # =============== Career vs Singleyr
    careerORSingleYr = html.Div([
        dbc.RadioItems(
            id = "careerORSingleYrRadio" + SUFFIX, 
            className = "btn-group", 
            inputClassName = "btn-check", 
            labelClassName = "btn btn-outline-primary", 
            labelCheckedClassName = "active", 
            value = True,
            options = [
                {"label": "Career", "value": True}, 
                {"label": "Single year", "value": False}, 
        ])], className = "radio-group")

    careerORSingleA1 = html.Div([
        dbc.RadioItems(
            id = "careerORSingleYrA1" + SUFFIX, 
            className = "btn-group", 
            inputClassName = "btn-check", 
            labelClassName = "btn btn-outline-primary", 
            labelCheckedClassName = "active", 
            value = True,
            options = [
                {"label": "Career", "value": True}, 
                {"label": "Single year", "value": False}, 
        ])], className = "radio-group")

    # =============== Year

    selectYr = html.Div(
        [dbc.RadioItems(
            id = "selectYrRadio" + SUFFIX, 
            className = "btn-group", 
            inputClassName = "btn-check", 
            labelClassName = "btn btn-outline-primary", 
            labelCheckedClassName = "active", 
            style = {'size':'sm'}, 
            value = 0,
            options = update_yr_options(career = True)
        )
    ], className = "radio-group year-picker")
    
    selectYrA1 = html.Div(
        [dbc.RadioItems(
            id = "selectYrRadioA1" + SUFFIX, 
            className = "btn-group", 
            inputClassName = "btn-check", 
            labelClassName = "btn btn-outline-primary", 
            labelCheckedClassName = "active", 
            style = {'size':'sm'}, 
            value = '2017',
            options = [{"label": "2017", "value": "2017", 'disabled': False}]
        )
    ], className = "radio-group year-picker")


    @callback(
        Output('selectYrRadio' + SUFFIX, 'options'), 
        Input('careerORSingleYrRadio' + SUFFIX, 'value'))
    def update_yr_opts(career):
        return(update_yr_options(career))

    # The "Select dataset" card that used to sit here was a large bordered box
    # whose whole content was the words "Select dataset", restating what the
    # control beside it already said. The two controls carry their own captions
    # now, in the same labelled-toolbar shape the home page uses.
    row1 = html.Div(
        [
            html.Div(
                [
                    html.Div(careerORSingleYr, className="ev-picker-left"),
                    html.Span(className="ev-picker-sep"),
                    html.Div(selectYr, className="ev-picker-right"),
                ],
                className="ev-picker",
            ),
        ],
        className="ev-toolbar ev-panel-toolbar",
    )

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 2 Select authors!
    # ========================================================================================== 
    # ========================================================================================== 

    author1Options = dcc.Dropdown(options = [], placeholder = 'Search researchers', multi = False, id = "author1OptionsDropdown" + SUFFIX, 
        value = default_author, searchable = True)
    generate_es_dropdown_callback("author1OptionsDropdown" + SUFFIX)
    generate_update_carsing_callback('author1OptionsDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX)
    generate_update_years_callback('careerORSingleYrA1' + SUFFIX, 'selectYrRadioA1' + SUFFIX, 'author1OptionsDropdown' + SUFFIX)
    output_ids = ['InfoAuthor1' + SUFFIX, 'FieldAuthor1' + SUFFIX, 'CountryAuthor1' + SUFFIX, 'InstitutionAuthor1' + SUFFIX]
    generate_update_cards_callback('selectYrRadioA1' + SUFFIX, output_ids, 'author1OptionsDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX,darkAccent1, highlight1)

    # What the gauges are measured against. The label used to be the whole
    # sentence, three times over ("Max and median (red) by country"), which
    # said the line was red when it is orange and left no room for the thing
    # a reader actually picks. The sentence is a legend under the gauges now
    # and names the group, so the control is just the group.
    upper = html.Div([
        html.Span('Compare against', className='ev-control-label'),
        dcc.Dropdown(
            options=[{'label': 'Country', 'value': 'cntry'},
                     {'label': 'Field', 'value': 'sm-field'},
                     {'label': 'Institution', 'value': 'inst_name'}],
            multi=False, id="upper" + SUFFIX, value='cntry',
            clearable=False, searchable=False),
    ], className='ev-compare')
 
   
    row2 = dbc.Container([
        dbc.Row(dbc.Col(html.Div([
            html.Div(author1Options, className="ev-author-search"),
            html.Div([
                html.Div(careerORSingleA1, className="ev-picker-left"),
                html.Span(className="ev-picker-sep"),
                html.Div(selectYrA1, className="ev-picker-right"),
            ], className="ev-picker ev-picker-inline"),
        ], className="ev-explore-bar"), width = 12), justify='center'),
        dbc.Row([
            dbc.Col(html.Center(id = 'InfoAuthor1' + SUFFIX), width = {'size':8}, style={'visibility':'hidden','height':'0px'})
        ], justify ='center'), dbc.Row([
            dbc.Col(html.Center(id = 'FieldAuthor1' + SUFFIX), width = {'size':8}, style={'visibility':'hidden','height':'0px'})
        ], justify ='center'), dbc.Row([
            dbc.Col(html.Center(id = 'CountryAuthor1' + SUFFIX), width = {'size':8}, style={'visibility':'hidden','height':'0px'})
        ], justify ='center'), dbc.Row([
            dbc.Col(html.Center(id = 'InstitutionAuthor1' + SUFFIX), width = {'size':8}, style={'visibility':'hidden','height':'0px'})
        ], justify ='center')
    ])

    # ========================================================================================== 
    # ========================================================================================== 
    # Main Author Figure
    # ========================================================================================== 
    # ========================================================================================== 
    # =============== Empty fig
    empty_fig = go.Figure()
    empty_fig.update_layout(height = 10, plot_bgcolor = bgc, paper_bgcolor = bgc)
    empty_fig.update_xaxes(visible = False)
    empty_fig.update_yaxes(visible = False)
    # =============== Toggle: log-transformed values!
    logTransf = daq.BooleanSwitch(label = 'Log transformed', labelPosition = 'bottom', id = 'logTransfToggleMain' + SUFFIX)
    # =============== Toggle: % self-citations
    selfC = daq.BooleanSwitch(label = 'Exclude self-citations', labelPosition = 'bottom', id = 'selfCToggle' + SUFFIX)
    # =============== Toggle: the what-if calculator
    whatIf = daq.BooleanSwitch(label = 'What if', labelPosition = 'bottom',
                               id = 'whatIfToggle' + SUFFIX,
                               color = WHATIF_BAR)
    whatIfStore = dcc.Store(id = 'whatIfStore' + SUFFIX)
    # =============== Figure title
    #figTitle = html.Div(' ', id = 'figTitleCard' + SUFFIX, style = {'color':lightAccent1, 'font-size':25})
    # =============== C score figure
    # =============== The author card
    #
    # Built as a shell here rather than inside the callback, because the
    # ECharts strip is drawn into #rankChart by a clientside callback and an
    # element Dash replaces on every author change is an element echarts has
    # already attached an instance to. The slots below are filled by
    # callbacks; the chart's own div is never destroyed.
    identityCard = html.Div([
        dcc.Store(id = 'rankChartStore' + SUFFIX),
        html.Div(id = 'cardHeader' + SUFFIX, className = 'ev-id-head'),
        html.Div([
            html.Div(id = 'rankDisplay' + SUFFIX, className = 'ev-id-ranks'),
            html.Div(id = 'rankChart' + SUFFIX, className = 'ev-rank-chart'),
        ], className = 'ev-id-body'),
        # The six indicators. The chart div is static for the same reason
        # #rankChart is: echarts attaches an instance to the element, and an
        # element Dash replaces on every author change is an element that
        # instance no longer points at. The input column beside it IS rebuilt
        # per author, because its values, caps and steps are the author's.
        html.Div([
            html.Div(id = 'bulletChart' + SUFFIX, className = 'ev-bullet-chart'),
            html.Div(id = 'bulletInputs' + SUFFIX,
                     className = 'ev-bullet-inputs'),
        ], className = 'ev-bullets'),
        dcc.Store(id = 'bulletStore' + SUFFIX),
        html.Div(id = 'bulletSink' + SUFFIX, style = {'display': 'none'}),
        html.Div(id = 'cardChips' + SUFFIX, className = 'ev-id-chips'),
        share_row(SUFFIX),
        dcc.Store(id = 'shareStore' + SUFFIX),
        html.Div(id = 'rankChartSink' + SUFFIX, style = {'display': 'none'}),
    ], id = 'idCard' + SUFFIX, className = 'ev-id-card')

    # ECharts is loaded from the CDN (see app.py) and lives entirely in the
    # browser, so the figure is drawn from a small payload rather than
    # shipped as JSON. Colours are read off the CSS custom properties at draw
    # time, which is the one thing the server-rendered plotly charts on this
    # page cannot do: this strip follows a theme switch.
    dash.clientside_callback(
        """
        function (payload, elementId) {
            var el = document.getElementById(elementId);
            if (!el || !window.echarts) { return ''; }

            // See the bullet chart above: named so a theme change can re-run
            // it, because the colours are read from CSS at draw time.
            function draw() {
            var chart = window.echarts.getInstanceByDom(el)
                        || window.echarts.init(el, null, {renderer: 'svg'});
            if (!payload) { chart.clear(); return; }

            var css = getComputedStyle(document.documentElement);
            function token(name, fallback) {
                var v = css.getPropertyValue(name);
                return (v && v.trim()) || fallback;
            }
            var muted = token('--ev-text-muted', '#A8B2C4');
            var accent = payload.whatif ? '#D86CB4' : token('--ev-accent', '#00B4D8');
            var orange = token('--ev-orange', '#F09048');
            var surface = token('--ev-surface-2', '#4A5670');

            function human(v) {
                if (v >= 1e6) { return (v / 1e6).toFixed(1) + 'M'; }
                if (v >= 1e3) { return Math.round(v / 1e3) + 'k'; }
                return String(v);
            }

            var ceiling = Math.max(payload.scopus_rank, payload.published);
            var span = ceiling * 1.15;
            // A label centred on a marker near either end of the axis runs
            // off the chart and is simply not drawn. A Scopus rank of
            // 908,824 on a list of 230,333 is exactly that case, and it is
            // the case the strip exists to show. So each label is anchored
            // away from whichever edge it is close to.
            function anchor(value) {
                var frac = Math.log(value) / Math.log(span);
                if (frac > 0.78) { return 'right'; }
                if (frac < 0.10) { return 'left'; }
                return 'center';
            }
            chart.setOption({
                animationDuration: 400,
                // The last axis tick sits at the maximum, so it needs room to
                       // its right or it is drawn half off the chart.
                grid: {left: 6, right: 20, top: 32, bottom: 6, containLabel: true},
                xAxis: {
                    type: 'log', min: 1, max: span,
                    axisLine: {show: false}, axisTick: {show: false},
                    splitLine: {lineStyle: {color: surface, opacity: 0.35}},
                    axisLabel: {color: muted, fontSize: 10,
                                formatter: function (v) { return human(v); }}
                },
                yAxis: {type: 'value', min: 0, max: 1, show: false},
                series: [
                    {
                        // The extent of the published list, rank 1 to the
                        // last person on it. Everything outside this bar was
                        // scored but not published.
                        type: 'line', silent: true, symbol: 'none', z: 1,
                        data: [[1, 0.5], [payload.published, 0.5]],
                        lineStyle: {width: 12, color: surface, cap: 'round'}
                    },
                    {
                        type: 'line', silent: true, symbol: 'none', z: 2,
                        data: [[1, 0.5], [payload.list_rank, 0.5]],
                        lineStyle: {width: 12, color: accent, opacity: 0.35,
                                    cap: 'round'}
                    },
                    {
                        type: 'scatter', z: 4, symbolSize: 16,
                        data: [[payload.list_rank, 0.5]],
                        itemStyle: {color: accent, shadowBlur: 16,
                                    shadowColor: accent},
                        label: {
                            show: true, position: 'top', distance: 8,
                            align: anchor(payload.list_rank),
                            color: accent, fontWeight: 600, fontSize: 11,
                            formatter: function (p) {
                                return human(p.value[0]) + ' on this list';
                            }
                        }
                    },
                    {
                        type: 'scatter', z: 3, symbolSize: 11,
                        data: [[payload.scopus_rank, 0.5]],
                        itemStyle: {color: orange},
                        label: {
                            show: true, position: 'bottom', distance: 8,
                            align: anchor(payload.scopus_rank),
                            color: orange, fontSize: 11,
                            formatter: function (p) {
                                return 'Scopus ' + human(p.value[0]);
                            }
                        }
                    }
                ]
            }, true);
            chart.resize();
            }

            el.__evRedraw = draw;
            window.__evCharts = window.__evCharts || [];
            if (window.__evCharts.indexOf(el) < 0) { window.__evCharts.push(el); }
            draw();
            return '';
        }
        """,
        Output('rankChartSink' + SUFFIX, 'children'),
        Input('rankChartStore' + SUFFIX, 'data'),
        State('rankChart' + SUFFIX, 'id'))

    # The share image is DRAWN, not captured.
    #
    # html2canvas and friends photograph the DOM, which here means a CSS mask
    # icon it cannot paint, a backdrop filter it cannot blur, and a strip
    # whose colours come from custom properties. Building the picture from
    # the same numbers the card shows avoids all of it, and the result is
    # sized for a social card rather than cropped from a page.
    #
    # It always prints the published figures. A what-if is an invention, and
    # an invention that leaves the site looking like a record is the one
    # outcome this whole page is built to prevent.
    dash.clientside_callback(
        """
        function (nx, nimg, ncopy, share, strip) {
            var trig = (dash_clientside.callback_context.triggered || [])[0];
            if (!trig || !share || !window.echarts) { return ''; }
            var what = trig.prop_id.split('.')[0];
            if (!trig.value) { return ''; }

            var W = 1200, H = 630;
            var BG = '#303C54', CARD = '#394459', TEXT = '#E8ECF2';
            var MUTED = '#A8B2C4', ACCENT = '#00B4D8', ORANGE = '#F09048';

            function human(v) {
                if (v >= 1e6) { return (v / 1e6).toFixed(1) + 'M'; }
                if (v >= 1e3) { return Math.round(v / 1e3) + 'k'; }
                return String(v);
            }
            function commas(v) {
                return (v === null || v === undefined) ? '-'
                    : v.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
            }

            var host = document.createElement('div');
            host.style.cssText = 'position:fixed;left:-99999px;top:0;width:'
                + W + 'px;height:' + H + 'px;';
            document.body.appendChild(host);
            var chart = window.echarts.init(host, null,
                {renderer: 'canvas', width: W, height: H});

            // `left` anchors an echarts graphic by its left edge, so a
            // right-aligned line still overflows the canvas and is cut off.
            // Anchoring from the right instead is what actually keeps it in.
            function text(x, y, str, size, colour, weight, fromRight) {
                var g = {type: 'text', top: y, silent: true,
                         style: {text: str, fontSize: size, fill: colour,
                                 fontWeight: weight || 'normal',
                                 fontFamily: 'system-ui, -apple-system, sans-serif'}};
                if (fromRight) { g.right = x; g.style.align = 'right'; }
                else { g.left = x; }
                return g;
            }

            var meta = [share.institute, share.country, share.field]
                       .filter(function (v) { return v; }).join('   ·   ');
            var graphics = [
                {type: 'rect', left: 0, top: 0, silent: true,
                 shape: {width: W, height: H}, style: {fill: BG}},
                {type: 'rect', left: 48, top: 44, silent: true,
                 shape: {width: W - 96, height: H - 88, r: 18},
                 style: {fill: CARD}},
                {type: 'rect', left: 48, top: 44, silent: true,
                 shape: {width: 6, height: H - 88}, style: {fill: ACCENT}},
                text(86, 86, share.name, 44, TEXT, 'bold'),
                text(86, 146, meta, 21, MUTED),
                text(86, 232, commas(share.list_rank), 76, ACCENT, 'bold'),
                text(86, 318, 'on this list', 22, TEXT, 'bold'),
                text(86, 348, 'of ' + commas(share.published) + ' published',
                     19, MUTED),
                text(430, 232, commas(share.scopus_rank), 76, ACCENT, 'bold'),
                text(430, 318, 'Scopus rank', 22, TEXT, 'bold'),
                text(430, 348, 'among everyone scored', 19, MUTED),
                text(86, H - 96, share.edition, 19, MUTED),
                text(86, H - 96, 'top 2% most-cited researchers', 19,
                     MUTED, 'normal', true)
            ];
            if (share.subfield) {
                graphics.push(text(750, 232, 'Subfield', 22, TEXT, 'bold'));
                graphics.push(text(750, 266, share.subfield, 19, MUTED));
            }
            if (share.self_pct !== null && share.self_pct !== undefined) {
                graphics.push(text(750, 318, 'Self-citations', 22, TEXT, 'bold'));
                graphics.push(text(750, 348, share.self_pct + '%', 19, MUTED));
            }

            var ceiling = Math.max(share.scopus_rank || 1, share.published || 1);
            chart.setOption({
                animation: false,
                graphic: graphics,
                grid: {left: 86, right: 86, top: H - 215, height: 56,
                       containLabel: false},
                xAxis: {
                    type: 'log', min: 1, max: ceiling * 1.15,
                    axisLine: {show: false}, axisTick: {show: false},
                    splitLine: {show: false},
                    axisLabel: {color: MUTED, fontSize: 14,
                                formatter: function (v) { return human(v); }}
                },
                yAxis: {type: 'value', min: 0, max: 1, show: false},
                series: [
                    {type: 'line', silent: true, symbol: 'none',
                     data: [[1, 0.6], [share.published, 0.6]],
                     lineStyle: {width: 14, color: '#4A5670', cap: 'round'}},
                    {type: 'line', silent: true, symbol: 'none',
                     data: [[1, 0.6], [share.list_rank, 0.6]],
                     lineStyle: {width: 14, color: ACCENT, opacity: 0.45,
                                 cap: 'round'}},
                    {type: 'scatter', symbolSize: 20, z: 4,
                     data: [[share.list_rank, 0.6]],
                     itemStyle: {color: ACCENT}},
                    {type: 'scatter', symbolSize: 14, z: 3,
                     data: [[share.scopus_rank, 0.6]],
                     itemStyle: {color: ORANGE}}
                ]
            }, true);

            var url = chart.getDataURL({type: 'png', pixelRatio: 2,
                                        backgroundColor: BG});
            chart.dispose();
            host.remove();

            var slug = (share.name || 'researcher').replace(/[^A-Za-z0-9]+/g, '-')
                       .replace(/^-|-$/g, '').toLowerCase();

            if (what.indexOf('shareX') === 0) {
                var line = share.name + ' ranks ' + commas(share.list_rank)
                    + ' of ' + commas(share.published) + ' on the top 2%'
                    + ' most-cited researchers list (' + share.edition + ').';
                window.open('https://twitter.com/intent/tweet?text='
                    + encodeURIComponent(line) + '&url='
                    + encodeURIComponent(window.location.origin), '_blank',
                    'noopener');
                return 'Opened X. Attach the downloaded card to the post.';
            }

            if (what.indexOf('shareImage') === 0) {
                var a = document.createElement('a');
                a.href = url;
                a.download = slug + '-' + (share.edition || 'card')
                             .replace(/[^A-Za-z0-9]+/g, '-') + '.png';
                document.body.appendChild(a);
                a.click();
                a.remove();
                return 'Card downloaded.';
            }

            if (what.indexOf('shareCopy') === 0) {
                if (!navigator.clipboard || !window.ClipboardItem) {
                    return 'This browser cannot copy images. Use Download.';
                }
                fetch(url).then(function (r) { return r.blob(); })
                  .then(function (blob) {
                    return navigator.clipboard.write(
                        [new ClipboardItem({'image/png': blob})]);
                  }).catch(function () {});
                return 'Card copied to the clipboard.';
            }
            return '';
        }
        """,
        Output('shareStatus' + SUFFIX, 'children'),
        Input('shareX' + SUFFIX, 'n_clicks'),
        Input('shareImage' + SUFFIX, 'n_clicks'),
        Input('shareCopy' + SUFFIX, 'n_clicks'),
        State('shareStore' + SUFFIX, 'data'),
        State('rankChartStore' + SUFFIX, 'data'),
        prevent_initial_call=True)

    # The bullet rows.
    #
    # Drawn in the browser so a what-if keystroke redraws without waiting on a
    # figure to come back over the wire, and so the colours can be read from
    # the CSS custom properties at draw time, which means the chart follows a
    # theme switch where the server-rendered plotly figures cannot.
    #
    # The geometry here is shared with assets/style.css: ROW and TOP set where
    # each bar sits, and .ev-bullet-inputs positions its boxes to match. If one
    # changes the other has to.
    dash.clientside_callback(
        """
        function (payload, elementId) {
            var el = document.getElementById(elementId);
            if (!el || !window.echarts) { return ''; }

            // Named so assets/charts.js can call it again when the theme
            // changes: the colours below are read from CSS at draw time, and
            // a chart already on screen does not redraw itself.
            function draw() {
            var chart = window.echarts.getInstanceByDom(el)
                        || window.echarts.init(el, null, {renderer: 'svg'});
            if (!payload || !payload.rows || !payload.rows.length) {
                chart.clear();
                return;
            }

            var ROW = 34, TOP = 26;
            var rows = payload.rows;
            var css = getComputedStyle(document.documentElement);
            function token(name, fallback) {
                var v = css.getPropertyValue(name);
                return (v && v.trim()) || fallback;
            }
            var accent = payload.whatif ? '#D86CB4'
                                        : token('--ev-accent', '#00B4D8');
            var orange = token('--ev-orange', '#F09048');
            var muted = token('--ev-text-muted', '#A8B2C4');
            var text = token('--ev-text', '#E8ECF2');
            var band = token('--ev-surface-2', '#4A5670');

            function commas(v) {
                var n = (Math.round(v * 10) / 10);
                var whole = Math.floor(n);
                var s = whole.toLocaleString();
                return (n - whole) ? s + (n - whole).toFixed(1).slice(1) : s;
            }

            var series = [
                // Spacer, then the group's middle half. A band drawn from q1
                // rather than from zero says where most of the group actually
                // sits, which a gauge could not show at all.
                // The group's middle half, drawn as a custom rect rather than
                // as a stacked bar. A stacked pair is its own bar group, and
                // echarts offsets bar groups within the category slot, so the
                // band sat half a row below the value it belongs to no matter
                // what barGap said. A custom series is positioned by hand
                // against the category centre, which is where the value bar
                // and the median tick already are.
                {type: 'custom', silent: true, z: 1,
                 renderItem: function (params, api) {
                     var row = api.value(0);
                     var a = api.coord([api.value(1), row]);
                     var b = api.coord([api.value(2), row]);
                     return {type: 'rect',
                             shape: {x: a[0], y: a[1] - 9,
                                     width: Math.max(b[0] - a[0], 1),
                                     height: 18},
                             style: {fill: band, opacity: 0.5}};
                 },
                 encode: {x: [1, 2], y: 0},
                 data: rows.map(function (r, i) { return [i, r.q1, r.q3]; })},
                // barGap -100% overlays this on the band instead of letting
                // echarts set it beside as a second bar group, which is what
                // put every value bar below the band it belongs to.
                {type: 'bar', barWidth: 8, barGap: '-100%', z: 3,
                 itemStyle: {color: accent, borderRadius: 2},
                 data: rows.map(function (r) { return r.share; }),
                 tooltip: {formatter: function (p) {
                     var r = rows[p.dataIndex];
                     return r.label + '<br/>' + commas(r.value)
                          + '<br/>contributes ' + r.share.toFixed(3)
                          + ' to the score'; }}},
                {type: 'scatter', symbol: 'rect', symbolSize: [3, 22], z: 4,
                 itemStyle: {color: orange},
                 data: rows.map(function (r, i) { return [r.median, i]; }),
                 tooltip: {formatter: function (p) {
                     var r = rows[p.dataIndex];
                     return 'median in ' + payload.group + '<br/>'
                          + (r.median_raw === null || r.median_raw === undefined
                             ? '-' : commas(r.median_raw)); }}}
            ];
            if (payload.whatif && payload.published) {
                // Where the real value sat before it was moved.
                series.push({type: 'scatter', symbol: 'circle', symbolSize: 7,
                    z: 5, itemStyle: {color: 'transparent',
                                      borderColor: token('--ev-accent', '#00B4D8'),
                                      borderWidth: 2},
                    data: payload.published.map(function (r, i) {
                        return [r.share, i]; }),
                    tooltip: {formatter: function (p) {
                        return 'published<br/>'
                             + commas(payload.published[p.dataIndex].value); }}});
            }

            chart.setOption({
                animationDuration: 260,
                // Room on the right for the input column, which is laid out
                // by CSS and sits over the chart.
                grid: {left: 150, right: 116, top: TOP, bottom: 8,
                       height: rows.length * ROW},
                tooltip: {trigger: 'item', backgroundColor: '#303C54',
                          borderColor: '#4A5670',
                          textStyle: {color: '#E8ECF2', fontSize: 12}},
                xAxis: {type: 'value', min: 0, max: 1, position: 'top',
                    axisLine: {show: false}, axisTick: {show: false},
                    axisLabel: {color: muted, fontSize: 10, formatter:
                        function (v) { return v === 1 ? 'edition max' : ''; }},
                    splitLine: {lineStyle: {color: band, opacity: 0.3}}},
                yAxis: {type: 'category', inverse: true,
                    data: rows.map(function (r) { return r.label; }),
                    axisLine: {show: false}, axisTick: {show: false},
                    axisLabel: {color: text, fontSize: 12}},
                series: series
            }, true);
            chart.resize();
            }

            el.__evRedraw = draw;
            window.__evCharts = window.__evCharts || [];
            if (window.__evCharts.indexOf(el) < 0) { window.__evCharts.push(el); }
            draw();
            return '';
        }
        """,
        Output('bulletSink' + SUFFIX, 'children'),
        Input('bulletStore' + SUFFIX, 'data'),
        State('bulletChart' + SUFFIX, 'id'))

    # =============== C score figure, beside the card
    metricsFigAuthor_c = dbc.Row([
        dbc.Col([html.Center(dcc.Graph(id = 'metricsFigGraphAuthor_c' + SUFFIX,
                                       figure = empty_fig,
                                       config = {'displayModeBar': False}))],
                md = 3),
        dbc.Col(identityCard, md = 8),
    ], justify = 'around')
    formulaRow = dbc.Row(dbc.Col(id = 'c_score_formula' + SUFFIX,
                                 width = {'offset': 1, 'size': 10}))

    # =============== The what-if boxes, one per bullet row
    def _bullet_inputs(state):
        """The six number boxes, aligned with the rows of the chart.

        They are the readout as well as the control: the value used to appear
        twice, once inside the gauge arc and again in a box underneath it.
        """
        cells = []
        for metric, label in WHATIF_METRICS:
            value = state['actual'].get(metric)
            # The h-index counts papers, so it cannot exceed the number of
            # papers. That ceiling is real and we know it, so the input
            # enforces it rather than letting someone claim an h-index of 900
            # from 120 papers. (It holds in the data too: h > np in 912 of
            # 1,402,942 published rows, so the cap is set above the published
            # value on the rare row where the publishers' own figure breaks
            # it.)
            maximum = None
            if metric == 'h' and state.get('np'):
                maximum = max(int(state['np']), int(value or 0))
            # Hm is a fractional h-index and the only one of the six that is
            # not a whole number. Everything else is a count, and a count in a
            # box reading 284984.0 looks like a bug.
            if value is not None:
                value = round(value, 1) if metric == 'hm' else int(value)
            # The tooltip goes on a wrapper: dbc.Input 1.3.1 rejects `title`
            # outright rather than passing it through to the <input>.
            cells.append(html.Div(
                dbc.Input(
                    id = 'whatIf-' + metric + SUFFIX, type = 'number',
                    value = value, min = 0, max = maximum,
                    step = 0.1 if metric == 'hm' else 1,
                    disabled = True, debounce = False,
                    className = 'ev-whatif-input'),
                title = label + (f' (max {maximum:,})' if maximum else '')))
        return cells

    def _whatif_note(state):
        if not state['reproducible']:
            return html.Div(
                'The what-if calculator is off for this edition: its '
                'published scores cannot be reproduced from the maxima '
                'recorded with it, so any score it computed here would '
                'disagree with the one printed above.',
                className = 'ev-whatif-note ev-whatif-note-off')
        return html.Div(
            'Change any of the six numbers and the composite score is '
            'recomputed with the published formula, then looked up in this '
            'edition. Nothing is predicted: this is where that score would '
            'have placed, holding the other indicators fixed. Real citations '
            'rarely move only one of them.',
            className = 'ev-whatif-note')

    # =============== Figure callbacks


    @callback(
        Output('2author_figs' + SUFFIX, 'children'), 
        Output('metricsFigGraphAuthor_c' + SUFFIX, 'figure'), 
        Output('c_score_formula' + SUFFIX, 'children'),
        Output('whatIfStore' + SUFFIX, 'data'),
        Output('whatIfToggle' + SUFFIX, 'on'),
        Output('cardHeader' + SUFFIX, 'children'),
        Output('cardChips' + SUFFIX, 'children'),
        Output('rankDisplay' + SUFFIX, 'children'),
        Output('rankChartStore' + SUFFIX, 'data'),
        Output('idCard' + SUFFIX, 'className'),
        Output('shareStore' + SUFFIX, 'data'),
        Output('gaugeLegend' + SUFFIX, 'children'),
        Output('bulletStore' + SUFFIX, 'data'),
        Output('bulletInputs' + SUFFIX, 'children'),
        [Input('careerORSingleYrA1' + SUFFIX, 'value'),
        Input('selectYrRadioA1' + SUFFIX,'value'),
        Input('selfCToggle' + SUFFIX, 'on'), 
        #Input('logTransfToggleMain' + SUFFIX, 'on'),
        Input('author1OptionsDropdown' + SUFFIX, 'value'), 
        Input("upper" + SUFFIX,'value')], 
        # Input('ncSlider1' + SUFFIX, 'value'), Input('hSlider1' + SUFFIX, 'value'), Input('hmSlider1' + SUFFIX, 'value'), 
        # Input('ncsSlider1' + SUFFIX, 'value'), Input('ncsfSlider1' + SUFFIX, 'value'), Input('ncsflSlider1' + SUFFIX, 'value'), 
        # Input('ncSlider2' + SUFFIX, 'value'), Input('hSlider2' + SUFFIX, 'value'), Input('hmSlider2' + SUFFIX, 'value'), 
        # Input('ncsSlider2' + SUFFIX, 'value'), Input('ncsfSlider2' + SUFFIX, 'value'), Input('ncsflSlider2' + SUFFIX, 'value'),
        #Input('ncWDD' + SUFFIX, 'value'), Input('hWDD' + SUFFIX, 'value'), Input('hmWDD' + SUFFIX, 'value'),
        #Input('ncsWDD' + SUFFIX, 'value'), Input('ncsfWDD' + SUFFIX, 'value'), Input('ncsflWDD' + SUFFIX, 'value')
        )
    # nc1, h1, hm1, ncs1, ncsf1, ncsfl1, nc2, h2, hm2, ncs2, ncsf2, ncsfl2
    def update_author_figso_and_rank(career1, yr1, ns, group1_name,uplim): # weights: ncW, hW, hmW, ncsW, ncsfW, ncsflW):
        '''
        group1_name: author name
        group2_name: author name
        '''
        if career1 == None or yr1 == None: raise PreventUpdate
        elif group1_name == None:
            return (["No dataset selected"], empty_fig, '', None, False,
                    card_header(None, None, None, None), [], [], None,
                    'ev-id-card', None, [], None, [])
        else:
            metrics_list = ['nc (ns)', 'h (ns)', 'hm (ns)',  'ncs (ns)', 'ncsf (ns)', 'ncsfl (ns)', 'c (ns)'] if ns else ['nc', 'h', 'hm',  'ncs', 'ncsf', 'ncsfl', 'c' ]
            prefix1 = 'career' if career1 else 'singleyr'
            # exact=True: the author name comes from the dropdown.
            results = get_es_results(group1_name, prefix1, 'authfull', exact=True)
            data1 = {}
            data1_log = {}
            if results is not None:
                data = es_result_pick(results, 'data', None)
                data1_log  = data[f'{prefix1}_{yr1}_log']
                data1 =  data[f'{prefix1}_{yr1}']
            logTransf = False
            

            names = get_inst_field_cntry(data, prefix1, yr1)
            # The stored country is a lowercase ISO3 code ("usa"), which is
            # what the aggregate lookups key on, but it is not what a reader
            # wants to see. coco turns it into a name for display only; the
            # code itself is still what gets passed to get_es_aggregate below.
            cntry_full = str(coco.convert(names=names['cntry'],
                                          to='name_short'))
            if cntry_full in ('not found', 'None'):
                cntry_full = str(names['cntry']).upper()
            # A rank means little without its denominator, and the denominator
            # has to be the right one.
            #
            # `rank` is the position in a ranking of EVERY scientist Scopus
            # scored, not of the people on this list. Verified: sorting a
            # career edition by rank leaves c monotonically non-increasing in
            # 100.00% of steps, so it is a strict global ordering by composite
            # score. In career-2024 the largest rank is 1,210,493 against
            # 230,333 published rows, and 48,401 rows (21%) carry a rank
            # larger than the list itself. Those people are published because
            # they are near the top of a SUBFIELD, not of the whole ranking:
            # their median subfield rank is 2,311 out of a median subfield of
            # 131,858.
            #
            # So pairing `rank` with the edition's size produced "ranked
            # 1,210,493 among 230,333 researchers", which is not just
            # unhelpful but visibly impossible, and it is the first thing a
            # reader notices. The subfield pair is a real one: rank_subfield
            # is at most subfield_count in 100.00% of rows.
            span = 'career-long up to' if prefix1 == 'career' else 'in'
            subfield = names.get('subfield') or data1.get('sm-subfield-1')
            sub_rank = data1.get('rank sm-subfield-1')
            sub_total = data1.get('sm-subfield-1 count')
            if sub_rank is not None and sub_total:
                # Components, not markdown: this used to be a markdown string
                # rendered by dcc.Markdown, and moving it into the card put
                # its asterisks on screen. The share image cannot draw
                # components, so it gets the same sentence as plain text.
                standing = [html.Strong(f'{int(sub_rank):,}'), ' of ',
                            html.Strong(f'{int(sub_total):,}'),
                            f' in {subfield}']
                standing_text = (f'{int(sub_rank):,} of {int(sub_total):,} '
                                 f'in {subfield}')
            else:
                # The 2017 and 2018 editions carry no subfield rank at all:
                # 210,026 rows, every one of them. Saying so beats the old
                # fallback, which printed the overall rank instead and so
                # repeated a number already on the card under a label
                # promising a different one.
                standing = 'Not recorded in this edition'
                standing_text = ''
            # Which group the gauges are scaled against, and the name of it,
            # which the legend has to print: "the median in Stanford
            # University" means something, "the median" does not.
            group_name = {'cntry': names['cntry'],
                          'sm-field': names['field'],
                          'inst_name': names['inst']}.get(uplim or 'cntry',
                                                          names['cntry'])
            kek = get_es_aggregate(uplim or 'cntry', group_name, prefix1)
            group_label = {'cntry': cntry_full,
                           'sm-field': names['field'],
                           'inst_name': names['inst']}.get(uplim or 'cntry',
                                                           cntry_full)

            max_metrics = {mt:[kek[f'{prefix1}_{yr1}'][mt][2],kek[f'{prefix1}_{yr1}'][mt][4]] for mt in metrics_list}
            # get_es_aggregate returns [min, q1, median, q3, max, n]. The
            # gauges only ever read the median and the max; the bullet rows
            # draw the group's middle half, so they need the quartiles too.
            quartiles = {
                metric: {'q1': kek[f'{prefix1}_{yr1}'][metric + suffix][1],
                         'median': kek[f'{prefix1}_{yr1}'][metric + suffix][2],
                         'q3': kek[f'{prefix1}_{yr1}'][metric + suffix][3]}
                for metric, _ in WHATIF_METRICS
                for suffix in [' (ns)' if ns else '']
            }
        # if career2 == True:
        #     dfs = dfs_career.copy()
        #     dfs_log = dfs_career_log.copy()
        # else:
        #     dfs = dfs_singleyr.copy()
        #     dfs_log = dfs_singleyr_log.copy()

            composite_fig, new_rank_1 = main_1_author_figs(
                data1, data1_log, group1_name, ns, logTransf, max_metrics,
                g1c = g1c, g2c = g2c, author1_metrics = {},
                author2_metrics = {})
            composite_fig.update_layout(height = 200)

            # Title
            title = 'Ranking based on composite score C and bar plots of metrics used to compute C'

            # =============== The two ranks
            #
            # Both numbers are computed here rather than read off the row,
            # because only one of them is published: `rank` counts everyone
            # Scopus scored, and the position on this list has to be counted.
            # Both ranks come from the researcher's own published score, in
            # the same lookup the what-if calculator uses. Counting ranks
            # below theirs would answer the same question and took 94 ms;
            # this takes 7, and it is one code path rather than two that
            # could disagree.
            rank_standing = score_standing(prefix1, yr1,
                                           data1.get('c' + (' (ns)' if ns
                                                            else '')),
                                           ns=ns)

            # =============== What-if state
            #
            # Everything the calculator needs, carried in the browser, so
            # moving an input does not repeat the Elasticsearch lookup that
            # found the author in the first place.
            suffix_ns = ' (ns)' if ns else ''

            def _number(value):
                return None if value is None else float(value)

            actual = {metric: _number(data1.get(metric + suffix_ns))
                      for metric, _ in WHATIF_METRICS}
            whatif_state = {
                'kind': prefix1, 'year': yr1, 'ns': bool(ns),
                'name': group1_name,
                'actual': actual,
                'np': _number(data1.get('np')),
                'maxima': composite_maxima(prefix1, yr1, ns=ns),
                'group_limits': {
                    metric: [_number(v)
                             for v in max_metrics[metric + suffix_ns]]
                    for metric, _ in WHATIF_METRICS},
                'c_limits': [_number(v) for v in max_metrics['c' + suffix_ns]],
                'standing': rank_standing,
                'reproducible': composite_is_reproducible(prefix1, yr1),
                'quartiles': {m: {k: _number(v) for k, v in q.items()}
                              for m, q in quartiles.items()},
                'group_label': str(group_label or ''),
            }

            figures = html.Div([_whatif_note(whatif_state)])
            rows = bullet_rows(actual, whatif_state['maxima'], quartiles)
            c_img = dbc.Container([dbc.Row(html.Br()), dbc.Row(dcc.Markdown(
                r'''
$$
C_i \;=\; \frac{\log(NC_i)}{\mathrm{maxlog}(NC)}
\;+\; \frac{\log(H_i)}{\mathrm{maxlog}(H)}
\;+\; \frac{\log(Hm_i)}{\mathrm{maxlog}(Hm)}
\;+\; \frac{\log(NCS_i)}{\mathrm{maxlog}(NCS)}
\;+\; \frac{\log(NCSF_i)}{\mathrm{maxlog}(NCSF)}
\;+\; \frac{\log(NCSFL_i)}{\mathrm{maxlog}(NCSFL)}
$$
''', mathjax=True, className='ev-formula'))])
            return (figures, composite_fig, c_img, whatif_state, False,
                    card_header(group1_name, names['inst'], cntry_full,
                                names['field'], f'{span} {yr1}'),
                    card_chips(round(data1['self%'] * 100, 2), standing),
                    rank_stats(rank_standing['scopus_rank'],
                               rank_standing['within_list'],
                               rank_standing['published']),
                    rank_chart_payload(rank_standing['within_list'],
                                       rank_standing['scopus_rank'],
                                       rank_standing['published']),
                    'ev-id-card',
                    share_payload(group1_name, names['inst'], cntry_full,
                                  names['field'], f'{span} {yr1}',
                                  rank_standing,
                                  round(data1['self%'] * 100, 2),
                                  standing_text),
                    gauge_legend(group_label),
                    bullet_payload(rows, group_label),
                    _bullet_inputs(whatif_state))

    def main_1_author_figs(df_in, df_in_log, group1_name, ns, logTransf, max_metrics, g1c = ['lightcoral', 'red'], g2c = ['lightblue', 'blue'], author1_metrics = {}, author2_metrics = {}, weights = [1, 1, 1, 1, 1, 1]):
        metrics_list = ['nc (ns)', 'h (ns)', 'hm (ns)',  'ncs (ns)', 'ncsf (ns)', 'ncsfl (ns)', 'c (ns)'] if ns else ['nc', 'h', 'hm',  'ncs', 'ncsf', 'ncsfl', 'c' ]
        
        if ns:
            cname  = 'c (ns)'
            rname  = 'rank (ns)'
        else:
            cname  = 'c'
            rname  = 'rank'
        
        logTransf = False
        # Get author 1 metrics to plot
        if group1_name != None:
            metrics_dict = get_initial_metrics_list(df_in, group1_name, ns)
            metrics_dict_log = get_initial_metrics_list(df_in_log, group1_name, ns)
            for key, value in author1_metrics.items():
                if ns: key += ' (ns)'
                metrics_dict[key] = value
            new_rank_1 = df_in[rname]
            new_y_values_1 = list(metrics_dict.values())
            new_y_values_1.append(df_in[cname])
            new_y_values_1_log = list(metrics_dict_log.values())
            new_y_values_1_log.append(df_in_log[cname])
            #print(new_y_values_1)
            # _, new_rank_1, new_y_values_1, _ = update_c_and_rank(df_in, author = group1_name, metrics_dict = metrics_dict, ns = ns, logTransf = False, weights = weights)
            # _, _, new_y_values_1_log, _ = update_c_and_rank(df_in, author = group1_name, metrics_dict = metrics_dict, ns = ns, logTransf = True, weights = weights)
        else:
            new_rank_1 = 0
            new_y_values_1 = [0]*7
            new_y_values_1_log = [0]*7
        
        def sizeof_number(number):
            """
            format values per thousands : K-thousands, M-millions, B-billions. 
            
            parameters:
            -----------
            number is the number you want to format
            currency is the prefix that is displayed if provided (€, $, £...)
            
            """
            if number >= 1000:
                return f"{int(number/1000)}k"
            else:
                return f"{int(number)}"


        # The gauges are built by gauge_figure at module level, which the
        # what-if callback calls too. One builder means a hypothetical gauge
        # cannot drift away from the published one it replaces.
        # Only the composite gauge is built here. The six indicator gauges it
        # used to return became the bullet rows in the author card, which are
        # drawn in the browser from a small payload; building six plotly
        # figures per author load and discarding them is pure cost.
        composite = gauge_figure(GAUGE_TITLES[6], new_y_values_1[6],
                                 max_metrics[metrics_list[6]])
        return(composite, new_rank_1)

    # ==========================================================================================
    # The what-if calculator
    # ==========================================================================================
    #
    # Everything here is arithmetic and one index lookup. The composite score
    # is recomputed with the published formula from whatever the reader typed,
    # and the standing is read off the researcher that score lands beside in
    # the same edition. No model, no extrapolation, nothing that could be
    # wrong in a way the page cannot show.

    @callback(
        [Output('bulletStore' + SUFFIX, 'data', allow_duplicate = True),
         Output('metricsFigGraphAuthor_c' + SUFFIX, 'figure',
                allow_duplicate = True),
           Output('rankDisplay' + SUFFIX, 'children', allow_duplicate = True),
           Output('rankChartStore' + SUFFIX, 'data', allow_duplicate = True),
           Output('idCard' + SUFFIX, 'className', allow_duplicate = True)]
        + [Output('whatIf-' + metric + SUFFIX, 'disabled')
           for metric, _ in WHATIF_METRICS],
        [Input('whatIfToggle' + SUFFIX, 'on')]
        + [Input('whatIf-' + metric + SUFFIX, 'value')
           for metric, _ in WHATIF_METRICS],
        State('whatIfStore' + SUFFIX, 'data'),
        prevent_initial_call = True)
    def apply_whatif(on, *args):
        typed, state = args[:len(WHATIF_METRICS)], args[-1]
        if not state:
            raise PreventUpdate

        live = bool(on) and state['reproducible']
        locked = [not live] * len(WHATIF_METRICS)
        standing = state['standing']

        published_rows = bullet_rows(state['actual'], state['maxima'],
                                     state['quartiles'])

        if not live:
            # Back to what was published, on the rows and on the rank at once.
            # Leaving one of them magenta is the failure this guards.
            published_c = composite_score(state['actual'], state['maxima'])
            return [
                bullet_payload(published_rows, state['group_label']),
                gauge_figure(GAUGE_TITLES[6], published_c, state['c_limits']),
                rank_stats(standing['scopus_rank'], standing['within_list'],
                           standing['published']),
                rank_chart_payload(standing['within_list'],
                                   standing['scopus_rank'],
                                   standing['published']),
                'ev-id-card',
            ] + locked

        # An emptied box means "leave this one alone", not zero. Someone
        # clearing a field to retype it should not watch the rank collapse
        # between keystrokes.
        values = {}
        for index, (metric, _) in enumerate(WHATIF_METRICS):
            entered = typed[index]
            values[metric] = (state['actual'][metric] if entered is None
                              else max(float(entered), 0.0))

        # An h-index cannot exceed the number of papers. `max` on the input
        # is only advisory, so the cap is applied here as well rather than
        # trusting the browser to have enforced it.
        if state.get('np'):
            ceiling = max(float(state['np']), state['actual']['h'] or 0)
            values['h'] = min(values['h'], ceiling)

        new_c = composite_score(values, state['maxima'])
        new_standing = score_standing(state['kind'], state['year'], new_c,
                                      ns = state['ns'])

        published_c = composite_score(state['actual'], state['maxima'])
        return [
            bullet_payload(bullet_rows(values, state['maxima'],
                                       state['quartiles']),
                           state['group_label'], whatif = True,
                           published = published_rows),
            gauge_figure(GAUGE_TITLES[6], new_c, state['c_limits'],
                         whatif = True, reference = published_c),
            rank_stats(new_standing['scopus_rank'],
                       new_standing['within_list'],
                       new_standing['published'], whatif = True,
                       was = {'list_rank': standing['within_list'],
                              'scopus_rank': standing['scopus_rank']}),
            rank_chart_payload(new_standing['within_list'],
                               new_standing['scopus_rank'],
                               new_standing['published'], whatif = True),
            'ev-id-card ev-id-card-whatif',
        ] + locked

    offcanvas2 = html.Div(
        [
            dbc.Offcanvas(
                dcc.Markdown(
                    '''
                * **User interactions**
                    * `Toggle`: Choose to exclude or include author self-citations
                    * `Dropdown`: Select a grouping by which the gauge limits will be set
                        * Country 
                        * Field 
                        * Institute
                * **Gauge indicators**
                    * Each indicator shows author's score for the respective metric (teal)
                    * The upper limits are determined by the MAXIMUM score of the selected group
                    * The red line shows the MEDIAN score of the selected group
                    * Delta under the current score indicates:
                        * Green (up): Author's score is higher than the group MEDIAN by ##
                        * Red (down): Author's score is lower than the group MEDIAN by ##
                    '''
                ),
                id="offcanvas22",
                title="Author metrics",
                is_open=False,
            ),
        ]
    )

    @callback(
        Output("offcanvas22", "is_open"),
        Input("open-offcanvas22", "n_clicks"),
        [State("offcanvas22", "is_open")],
    )
    def toggle_offcanvas(n1, is_open):
        if n1:
            return not is_open
        return is_open

    row3 = html.Div([
        whatIfStore,
        dbc.Row(html.Br()),
        dbc.Row(dbc.Col(html.Div([
            selfC, whatIf, upper,
            dbc.Button("More info", id="open-offcanvas22", n_clicks=0,
                       className="ev-info-btn"),
        ], className="ev-explore-controls"), width = 12)),
        dbc.Row(dbc.Col(html.Div(id='gaugeLegend' + SUFFIX,
                                 className='ev-gauge-legend'), width = 12)),
        metricsFigAuthor_c,
        dbc.Row(html.Br()),
        formulaRow,
        dbc.Row(html.Br()),
        offcanvas2,
        dbc.Row(dbc.Col(dbc.Container(id = '2author_figs' + SUFFIX), width = {'offset':1,'size':10}))])

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 4: author playground
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Metric weighting dropdown
    # ncW = dcc.Dropdown(value = 1, options = list(range(11)), style = {'background-color':darkAccent3}, id = 'ncWDD' + SUFFIX)
    # hW = dcc.Dropdown(value = 1, options = list(range(11)), style = {'background-color':darkAccent3}, id = 'hWDD' + SUFFIX)
    # hmW = dcc.Dropdown(value = 1, options = list(range(11)), style = {'background-color':darkAccent3}, id = 'hmWDD' + SUFFIX)
    # ncsW = dcc.Dropdown(value = 1, options = list(range(11)), style = {'background-color':darkAccent3}, id = 'ncsWDD' + SUFFIX)
    # ncsfW = dcc.Dropdown(value = 1, options = list(range(11)), style = {'background-color':darkAccent3}, id = 'ncsfWDD' + SUFFIX)
    # ncsflW = dcc.Dropdown(value = 1, options = list(range(11)), style = {'background-color':darkAccent3}, id = 'ncsflWDD' + SUFFIX)

    # =============== Slider labels
    # ncButton1 = dbc.Card(html.Center('NC', style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
    # hButton1 = dbc.Card(html.Center('H', style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
    # hmButton1 = dbc.Card(html.Center('Hm', style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
    # ncsButton1 = dbc.Card(html.Center('NCS', style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
    # ncsfButton1 = dbc.Card(html.Center('NCSF', style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
    # ncsflButton1 = dbc.Card(html.Center('NCSFL', style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
    # ncButton2 = dbc.Card(html.Center('NC', style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
    # hButton2 = dbc.Card(html.Center('H', style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
    # hmButton2 = dbc.Card(html.Center('Hm', style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
    # ncsButton2 = dbc.Card(html.Center('NCS', style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
    # ncsfButton2 = dbc.Card(html.Center('NCSF', style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
    # ncsflButton2 = dbc.Card(html.Center('NCSFL', style = {'color':darkAccent1, 'font-size':18}), color = highlight2)

    # =============== Metrics sliders
    # def update_metric_slider(career, yr, ns, metric):
    #     f_out = 'career' if career == True else 'singleyr'
    #     fns_out = ' (ns)' if ns == True else ''
    #     max = int(dropdown_opts[f_out + ' ' + str(yr)][metric + fns_out + ' max'])
    #     step = math.floor(max/math.floor(vert_slider_length/20))
    #     return [max, step]
    # def update_metric_slider_val(career, yr, ns, author, metric):
    #     dfs = dfs_career.copy() if career == True else dfs_singleyr.copy()
    #     fns_out = ' (ns)' if ns == True else ''
    #     return(float(dfs[yr][dfs[yr]['authfull'] == author][metric + fns_out]))

    # nc1 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'ncSlider1' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # h1 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'hSlider1' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # hm1 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'hmSlider1' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # ncs1 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'ncsSlider1' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # ncsf1 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'ncsfSlider1' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # ncsfl1 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'ncsflSlider1' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # nc2 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'ncSlider2' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # h2 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'hSlider2' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # hm2 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'hmSlider2' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # ncs2 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'ncsSlider2' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # ncsf2 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'ncsfSlider2' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # ncsfl2 = dcc.Slider(min = 0, max = 0, step = 0, value = 0, tooltip = {"placement": "bottom", "always_visible": True}, id = 'ncsflSlider2' + SUFFIX, vertical = True, verticalHeight = vert_slider_length)
    # @callback(
    #     Output('ncSlider1' + SUFFIX, 'max'), Output('ncSlider1' + SUFFIX, 'step'), 
    #     Output('hSlider1' + SUFFIX, 'max'), Output('hSlider1' + SUFFIX, 'step'), 
    #     Output('hmSlider1' + SUFFIX, 'max'), Output('hmSlider1' + SUFFIX, 'step'), 
    #     Output('ncsSlider1' + SUFFIX, 'max'), Output('ncsSlider1' + SUFFIX, 'step'), 
    #     Output('ncsfSlider1' + SUFFIX, 'max'), Output('ncsfSlider1' + SUFFIX, 'step'), 
    #     Output('ncsflSlider1' + SUFFIX, 'max'), Output('ncsflSlider1' + SUFFIX, 'step'), 
    #     Output('ncSlider2' + SUFFIX, 'max'), Output('ncSlider2' + SUFFIX, 'step'), 
    #     Output('hSlider2' + SUFFIX, 'max'), Output('hSlider2' + SUFFIX, 'step'), 
    #     Output('hmSlider2' + SUFFIX, 'max'), Output('hmSlider2' + SUFFIX, 'step'), 
    #     Output('ncsSlider2' + SUFFIX, 'max'), Output('ncsSlider2' + SUFFIX, 'step'), 
    #     Output('ncsfSlider2' + SUFFIX, 'max'), Output('ncsfSlider2' + SUFFIX, 'step'), 
    #     Output('ncsflSlider2' + SUFFIX, 'max'), Output('ncsflSlider2' + SUFFIX, 'step'), 
    #     Input('careerORSingleYrRadio' + SUFFIX, 'value'), 
    #     Input('selectYrRadio' + SUFFIX, 'value'), 
    #     Input('selfCToggle' + SUFFIX, 'on'))
    # def update_slider(career, yr, ns):
    #     if career == None or yr == None: return(list(np.zeros(24)))
    #     else:
    #         return update_metric_slider(career, yr, ns, 'nc') + update_metric_slider(career, yr, ns, 'h') + update_metric_slider(
    #             career, yr, ns, 'hm') + update_metric_slider(career, yr, ns, 'ncs') + update_metric_slider(
    #             career, yr, ns, 'ncsf') + update_metric_slider(career, yr, ns, 'ncsfl') + update_metric_slider(
    #             career, yr, ns, 'nc') + update_metric_slider(career, yr, ns, 'h') + update_metric_slider(
    #             career, yr, ns, 'hm') + update_metric_slider(career, yr, ns, 'ncs') + update_metric_slider(
    #             career, yr, ns, 'ncsf') + update_metric_slider(career, yr, ns, 'ncsfl')
    # @callback(
    #     Output('ncSlider1' + SUFFIX, 'value'), 
    #     Output('hSlider1' + SUFFIX, 'value'), 
    #     Output('hmSlider1' + SUFFIX, 'value'), 
    #     Output('ncsSlider1' + SUFFIX, 'value'), 
    #     Output('ncsfSlider1' + SUFFIX, 'value'), 
    #     Output('ncsflSlider1' + SUFFIX, 'value'), 
    #     Input('careerORSingleYrRadio' + SUFFIX, 'value'), 
    #     Input('selectYrRadio' + SUFFIX, 'value'), 
    #     Input('selfCToggle' + SUFFIX, 'on'), 
    #     Input('author1OptionsDropdown' + SUFFIX, 'value'), 
    #     Input('sliderResetButton' + SUFFIX, 'n_clicks'))
    # def update_slider_val(career, yr, ns, group1_name, sliderResetButton):
    #     if career == None or yr == None or group1_name == None: return(list(np.zeros(6)))
    #     else: return [update_metric_slider_val(career, yr, ns, group1_name, metric = 'nc'), update_metric_slider_val(career, yr, ns, group1_name, metric = 'h'), 
    #         update_metric_slider_val(career, yr, ns, group1_name, metric = 'hm'), update_metric_slider_val(career, yr, ns, group1_name, metric = 'ncs'), 
    #         update_metric_slider_val(career, yr, ns, group1_name, metric = 'ncsf'), update_metric_slider_val(career, yr, ns, group1_name, metric = 'ncsfl')]
    # @callback(
    #     Output('ncSlider2' + SUFFIX, 'value'), 
    #     Output('hSlider2' + SUFFIX, 'value'), 
    #     Output('hmSlider2' + SUFFIX, 'value'), 
    #     Output('ncsSlider2' + SUFFIX, 'value'), 
    #     Output('ncsfSlider2' + SUFFIX, 'value'), 
    #     Output('ncsflSlider2' + SUFFIX, 'value'), 
    #     Input('careerORSingleYrRadio' + SUFFIX, 'value'), 
    #     Input('selectYrRadio' + SUFFIX, 'value'), 
    #     Input('selfCToggle' + SUFFIX, 'on'), 
    #     Input('author2OptionsDropdown' + SUFFIX, 'value'), 
    #     Input('sliderResetButton' + SUFFIX, 'n_clicks'))
    # def update_slider_val(career, yr, ns, group2_name, sliderResetButton):
    #     if career == None or yr == None or group2_name == None: return(list(np.zeros(6)))
    #     else: return [update_metric_slider_val(career, yr, ns, group2_name, metric = 'nc'), update_metric_slider_val(career, yr, ns, group2_name, metric = 'h'), 
    #         update_metric_slider_val(career, yr, ns, group2_name, metric = 'hm'), update_metric_slider_val(career, yr, ns, group2_name, metric = 'ncs'), 
    #         update_metric_slider_val(career, yr, ns, group2_name, metric = 'ncsf'), update_metric_slider_val(career, yr, ns, group2_name, metric = 'ncsfl')]

    # row4 = dbc.Row([html.Div([
    #     html.Br(),
    #     dbc.Button("Author playground", 
    #         id = "collapse-button4" + SUFFIX, className = "mb-3", color = "primary", n_clicks = 0), 
    #     # dbc.Collapse(
    #     #     dbc.Container(fluid = True, children = [
    #     #         #dbc.Row([dbc.Col(html.Center(['Use dropdowns to modify the extent to which each metric impacts the composite score C'], style = {'color':lightAccent1, 'size':20}))]), 
    #     #         dbc.Row([dbc.Col(html.Center(['Use the sliders to modify author metric values! You can always ', html.Button('Reset', id = 'sliderResetButton' + SUFFIX, n_clicks = 0), ' these values!'], style = {'color':lightAccent1, 'size':20}))]), 
    #     #         # dbc.Row(html.Br()), 
    #     #         # dbc.Row(dbc.Col(dbc.Container([dbc.Row([
    #     #         #     dbc.Col([html.Center(['NC weighting'], style = {'font-weight': 'bold'}), html.Center(ncW)], width = 2), 
    #     #         #     dbc.Col([html.Center(['H weighting'], style = {'font-weight': 'bold', "text-align": "center"}), html.Center(hW)], width = 2), 
    #     #         #     dbc.Col([html.Center(['Hm weighting'], style = {'font-weight': 'bold', "text-align": "center"}), html.Center(hmW)], width = 2), 
    #     #         #     dbc.Col([html.Center(['NCS weighting'], style = {'font-weight': 'bold', "text-align": "center"}), html.Center(ncsW)], width = 2), 
    #     #         #     dbc.Col([html.Center(['NCSF weighting'], style = {'font-weight': 'bold', "text-align": "center"}), html.Center(ncsfW)], width = 2), 
    #     #         #     dbc.Col([html.Center(['NCSFL weighting'], style = {'font-weight': 'bold', "text-align": "center"}), html.Center(ncsflW)], width = 2), 
    #     #         # ])]),width = {'offset':1,'size':10})), 
    #     #         dbc.Row(html.Br()), 
    #     #         dbc.Row(dbc.Col(dbc.Container([dbc.Row([
    #     #             dbc.Col([html.Center(ncButton1), html.Center(nc1)], width = 1), dbc.Col([html.Center(ncButton2), html.Center(nc2)], width = 1), 
    #     #             dbc.Col([html.Center(hButton1), html.Center(h1)], width = 1), dbc.Col([html.Center(hButton2), html.Center(h2)], width = 1), 
    #     #             dbc.Col([html.Center(hmButton1), html.Center(hm1)], width = 1), dbc.Col([html.Center(hmButton2), html.Center(hm2)], width = 1), 
    #     #             dbc.Col([html.Center(ncsButton1), html.Center(ncs1)], width = 1), dbc.Col([html.Center(ncsButton2), html.Center(ncs2)], width = 1), 
    #     #             dbc.Col([html.Center(ncsfButton1), html.Center(ncsf1)], width = 1), dbc.Col([html.Center(ncsfButton2), html.Center(ncsf2)], width = 1), 
    #     #             dbc.Col([html.Center(ncsflButton1), html.Center(ncsfl1)], width = 1), dbc.Col([html.Center(ncsflButton2), html.Center(ncsfl2)], width = 1)
    #     #         ])]),width = {'offset':1,'size':10})), 
    #     # ], style = {'backgroundColor':darkAccent1}), 
    #     # id = "collapse4" + SUFFIX, 
    #     # is_open = False, 
    #     # )
    #     ])])
    # @callback(
    #     Output("collapse4" + SUFFIX, "is_open"), 
    #     [Input("collapse-button4" + SUFFIX, "n_clicks")], 
    #     [State("collapse4" + SUFFIX, "is_open")], )
    # def toggle_collapse(n, is_open):
    #     if n:
    #         return not is_open
    #     return is_open

    # ========================================================================================== 
    # ========================================================================================== 
    # Layout
    # ========================================================================================== 
    # ========================================================================================== 
    return(html.Div([
        dbc.Container(fluid = True, children = [
            #row1, 
            html.Br(),
            row2, 
            dls.GridFade(row3,color="#ECAB4C"), 
        ], className = 'ev-page'), 
    ]))