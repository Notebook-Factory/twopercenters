# ========================================================================================== 
# ========================================================================================== 
# IMPORT LIBRARIES
# ========================================================================================== 
# ========================================================================================== 

# =============== misc libs & modules
import numpy as np
import math
import pickle
import plotly.io as pio
# =============== Plotly libs & modules
import plotly.graph_objects as go
import plotly.express as px
# =============== Plotly Dash libraries
import dash
from dash import html, dcc, callback, dash_table, callback_context #, Input, Output
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq
import dash_loading_spinners as dls

# =============== Custom lib
from citations_lib.create_fig_helper_functions import *
from citations_lib.utils import *
from citations_lib.glowmap import glow_map
from citations_lib.utils import city_points, city_researchers
from citations_lib.top10 import top10_layout
from citations_lib.single_author_layout import *
from citations_lib.author_vs_group_layout import *
from citations_lib.group_vs_group_layout import *
from citations_lib.author_vs_author_layout import *
from citations_lib.auth_find import *


# =============== Register page
# name is what dash.page_registry and the nav label show; without it Dash
# derives it from the module filename, which made this page "Home".
# title is what the browser tab says.
dash.register_page(__name__, path='/', name='Twopercenters',
                   title='Twopercenters')
SUFFIX = "HOME"
# FOR TESTING ONLY:
# layout = html.Div([dbc.Container(fluid = True, children = [dbc.Row(dbc.Col(dbc.Button('Testing ground', href = '/test', target = '_blank'), width = 1))])])

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
theme =  {'dark': True, 'detail': lightAccent1, 'primary': darkAccent1, 'secondary': lightAccent1}

g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
g2c = [highlight2, darkAccent3] # bar plot bar 3
# Transparent, not a colour: the page's own background shows through, so
# a chart follows the light/dark switch without being redrawn.
bgc = 'rgba(0,0,0,0)' # chart background: inherit the page

# The United States contributes 87,859 researchers to career-2024. Sending
# all of them made a 7.2 MB response that the browser had to parse and render,
# which is why clicking a large country looked like nothing happening. A page
# of names is what this table is for; the true total is shown beside it, and
# the spotlight search is the way to reach a specific person.
COUNTRY_ROW_LIMIT = 500

tbl  = dash_table.DataTable(
    id = 'instnametable',
    #filter_action="native",
    fixed_rows={'headers': True},
    #filter_options={"placeholder_text": "Filter column..."},
    #style_table={'overflowX': 'auto'},
        # These two were still the old ocre and a hardcoded rgb(50,50,50):
    # literals, so the palette sweep did not reach them, and they ignored the
    # theme. Inline styles take var(), so they follow it now.
    style_header={
        'backgroundColor': 'var(--ev-surface-2)',
        'color': 'var(--ev-text)',
        'fontWeight': '600',
        'border': 'none',
        'borderBottom': '1px solid var(--ev-surface-2)',
        'padding': '10px 12px',
    },
    style_data={
        'backgroundColor': 'transparent',
        'color': 'var(--ev-text)',
        'border': 'none',
        'borderBottom': '1px solid var(--ev-surface-2)',
    },
    style_table={'height': '300px', 'overflowY': 'auto','display':'none'},
    page_action='native',
    page_size=20,
    sort_action='native',
    style_cell={
        'height': 'auto',
        'textAlign': 'left',
        'maxWidth': '0',
        'whiteSpace': 'normal',
        'padding': '10px 12px',
        'fontSize': '0.9rem',
        'fontFamily': 'inherit',
    }
)


@callback(
    Output('worldtitle', 'children',allow_duplicate=True),
    [Input('instnametable', 'active_cell')],
    [State('selectYrRadio' + SUFFIX, 'value'),
     State("careerORSingleYrRadio" + SUFFIX, 'value'),
     State("stats2", 'value'),
     State('instnametable', 'data')],
    prevent_initial_call='initial_duplicate')
def update_graphs(val,yr, iscar, sts,dt):
    if val is None:
        raise PreventUpdate
    else:
        if sts == 'median':
            st_idx = 2
        elif sts == 'min':
            st_idx = 0
        elif sts == 'max':
            st_idx = 4
        elif sts == '25':
            st_idx = 1
        elif sts == '75':
            st_idx = 3
        if iscar:
            prefix = 'career'
            txt = 'career-long up to'
        else:
            prefix = 'singleyr'
            txt = 'single-year in '
        
        sel_type = val['column_id']
        selection = dt[val['row']][sel_type]
        
        if sel_type == 'RESEARCHER':
            # exact=True: `selection` is a RESEARCHER cell from the country
            # table, which country_researchers filled from authors.authfull_display.
            results = get_es_results(selection,prefix,'authfull',exact=True)
            if results is not None:
                data = es_result_pick(results, 'data', None)
                data  = data[f'{prefix}_{yr}']
                self_cit = f'''
                ---
                ##### Summary for **{selection.split(',')[0]}** {txt} {yr}
                - `Number of citations:` **{int(data['nc'])}**
                - `H-index:` **{int(data['h'])}**
                - `Hm-index:` **{int(data['hm'])}**
                - `Self citation ratio:` **{np.round(data['self%']*100,2)}%**
                '''
        elif sel_type == 'INSTITUTE':
            data = get_es_aggregate('inst_name',selection,prefix)
            data = data[f'{prefix}_{yr}']
            self_cit = f'''
                ---
                ##### Summary ({sts}) for **{selection}** {txt} {yr}
                - `Number of citations:` **{int(data['nc'][st_idx])}**
                - `H-index:` **{int(data['h'][st_idx])}**
                - `Hm-index:` **{int(data['hm'][st_idx])}**
                - `Self citation ratio:` **{np.round(data['self%'][st_idx]*100,2)}%**
                '''
        return self_cit

compare_row = html.Div([
    dbc.Row([
        dbc.Col([html.Center(dbc.Button("🔸 Author 🆚 author", className="me-2", id = "collapse_btn_author_vs_author",
            style={"color": lightAccent1, 'font-size':'17px', "fontWeight": "bold", "border-color": lightAccent1,"border-radius":"30px", "border-width":"2px", "background-image": "linear-gradient(to bottom, #2C2C2C, #5b5959)"},
            n_clicks = 0, color = darkAccent1))], width = 3),
        dbc.Col([html.Center(dbc.Button("🔸 Group 🆚 group", className="me-2", id = "collapse_btn_group_vs_group",
            style={"color": lightAccent1, 'font-size':'17px', "fontWeight": "bold", "border-color": lightAccent1,"border-radius":"30px", "border-width":"2px", "background-image": "linear-gradient(to bottom, #2C2C2C, #5b5959)"},
            n_clicks = 0, color = darkAccent1))], width = 3),
        dbc.Col([html.Center(dbc.Button("🔸 Author 🆚 group", className="me-2", id = "collapse_btn_author_vs_group",
            style={"color": lightAccent1, 'font-size':'17px', "fontWeight": "bold", "border-color": lightAccent1,"border-radius":"30px", "border-width":"2px", "background-image": "linear-gradient(to bottom, #2C2C2C, #5b5959)"},
            n_clicks = 0, color = darkAccent1))], width = 3),
    ], justify="center"),
    dbc.Row([dbc.Col(dbc.Collapse(dbc.Container(fluid = True, children = [author_vs_author_layout()], className = 'ev-page'), 
        id = "collapse_author_vs_author", is_open = False))], className="mt-3"),
    dbc.Row([dbc.Col(dbc.Collapse(dbc.Container(fluid = True, children = [author_vs_group_layout()], className = 'ev-page'), 
         id = "collapse_author_vs_group", is_open = False))], className="mt-3"),
    dbc.Row([dbc.Col(dbc.Collapse(dbc.Container(fluid = True, children = [group_vs_group_layout(),author_find_layout()], className = 'ev-page'), 
        id = "collapse_group_vs_group", is_open = False))], className="mt-3")
    ])


"""
World map interactions
"""


def _clicked_a_city(city, country_code, is_career, yr):
    """One city's researchers, in the same shape the country view uses.

    There is no aggregate for a city, because the summaries this dashboard
    keeps are per country, field and institution. What a city does have is
    the people in it, so the summary says what can be counted directly and
    the table lists them, best score first.
    """
    kind = 'career' if is_career else 'singleyr'
    rows, total = city_researchers(city, country_code, kind, yr,
                                   limit=COUNTRY_ROW_LIMIT)
    if not rows:
        raise PreventUpdate
    points = [p for p in city_points(kind, int(yr))
              if p['city'] == city and p['country_code'] == country_code]
    place = points[0] if points else None
    when = f"Career-long up to {yr}" if is_career else f"Single-year data in {yr}"
    country_full = str(coco.convert(names=country_code, to='name_short'))
    if country_full in ('not found', 'None'):
        country_full = country_code
    if place:
        summary = f"""
                ---
                ##### **{city}, {country_full}**
                - `Researchers on the list:` **{place['researchers']:,}**
                - `Citations, summed:` **{place['citations']:,}**
                - `Papers, summed:` **{place['papers']:,}**
                - `Best h-index here:` **{place['h']}**
               """
    else:
        summary = f"""
                ---
                ##### **{city}, {country_full}**
                - `Researchers on the list:` **{total:,}**
               """
    shown = len(rows)
    listing = (f'<strong>{shown:,}</strong> of <strong>{total:,}</strong> '
               f'researchers, by score' if total > shown
               else f'<strong>{total:,}</strong> researchers')
    message = (f'<div class="danger"><center><strong>{when}</strong><br/>'
               f'{listing} in <strong>{city}</strong>'
               f'<br/><u>Click a row to see that researcher</u></center></div>')
    return (summary, rows, message,
            {'height': '400px', 'overflowY': 'auto', 'display': 'block'},
            [], None)
@callback(
    Output('worldtitle', 'children',allow_duplicate=True),
    Output('instnametable','data'),
    Output('cntrylabel','children'),
    Output('instnametable','style_table'),
    Output("instnametable", "selected_cells"),
    Output("instnametable", "active_cell"),
    Input('glowPicked_glowmap_', 'value'),
    Input("careerORSingleYrRadio" + SUFFIX, 'value'),
    Input("selectYrRadio" + SUFFIX, 'value'),
    Input('stats2', 'value'),
    #prevent_initial_call=True
    prevent_initial_call='initial_duplicate' 
    )
def click_on_map_update(val,is_career,yr,sts):
    """What the summary and the table show when a place is clicked.

    The map sends 'country|USA' or 'city|London|GBR', with a counter on the
    end so that clicking the same place twice is still a change Dash can
    see. A country reads from the Elasticsearch aggregates, which is what
    they exist for; a city reads from institution_ror, which is where the
    coordinates that put the point on the map came from.
    """
    if not val:
        raise PreventUpdate
    parts = str(val).split('|')
    if len(parts) < 2:
        raise PreventUpdate
    if parts[0] == 'city':
        return _clicked_a_city(parts[1], parts[2], is_career, yr)
    val = {'points': [{'location': parts[1]}]}
    if sts == 'median':
        st_idx = 2
    elif sts == 'min':
        st_idx = 0
    elif sts == 'max':
        st_idx = 4
    elif sts == '25':
        st_idx = 1
    elif sts == '75':
        st_idx = 3
    if is_career:
        cr = 'career'
    else:
        cr = 'singleyr'
    cntry = val['points'][0]['location'].lower()
    data = get_es_aggregate('cntry',cntry,cr)
    self_cit = f'''
                ---
                ##### Summary statistics ({sts}) for **{cntry.upper()}**
                - `Number of citations:` **{int(data[f'{cr}_{yr}']['nc'][st_idx])}**
                - `H-index:` **{int(data[f'{cr}_{yr}']['h'][st_idx])}**
                - `Hm-index:` **{int(data[f'{cr}_{yr}']['hm'][st_idx])}**
                - `Self citation ratio:` **{np.round(data[f'{cr}_{yr}']['self%'][st_idx]*100,2)}%**
               '''
    if is_career: 
        nm = 'career'
        txt = f"Career-long up to {yr}"
    else:
        nm = 'singleyr'
        txt = f"Single-year data in {yr}"

    # This used to scroll the legacy `career`/`singleyr` Elasticsearch
    # indices and filter each document on a `years` field. Those indices
    # stop at 2021 and only survive on this machine as the latency
    # benchmark's baseline, so selecting 2022, 2023 or 2024 and clicking a
    # country listed nobody. country_researchers asks Postgres, where the
    # fact rows actually live, for the same thing.
    # The table gets a page's worth, not the whole country. The count below
    # is the true total, queried separately.
    total_in_country = country_researcher_count(cntry, nm, yr)
    career_all_c = country_researchers(cntry, nm, yr, limit=COUNTRY_ROW_LIMIT)
    # The code is what the lookups key on; the name is what a reader wants.
    cntry_full = str(coco.convert(names=cntry, to='name_short'))
    if cntry_full in ('not found', 'None'):
        cntry_full = cntry.upper()
    total_authors = edition_author_count(nm, yr)
    shown = len(career_all_c)
    if total_in_country > shown:
        listing = (f'<strong>{shown:,}</strong> of '
                   f'<strong>{total_in_country:,}</strong> researchers, '
                   f'alphabetically')
    else:
        listing = f'<strong>{total_in_country:,}</strong> researchers'
    msg = (f'<div class="danger"><center><strong>{txt}</strong><br/>'
           f'{listing} in <strong>{cntry_full}</strong>'
           f'<br/><span class="ev-of-total">{total_authors:,} worldwide '
           f'in this selection</span>'
           f'<br/><u>Click a row to see that researcher</u></center></div>')
    return(self_cit,career_all_c, msg, {'height': '400px', 'overflowY': 'auto','display':'block'},[],None)

# The map's opening frame. Was pinned to '2021'; it follows the most recent
# career edition now, so loading a new edition moves it without an edit here.
_MAP_YEAR_OPTIONS, _MAP_DEFAULT_YEAR = update_yr_options2(True)

# The plotly choropleth that used to live here is gone: the echarts map in
# citations_lib/glowmap.py took its place, which reads at two granularities
# rather than one and can be clicked down to a city. What stays is the
# toolbar above it, because the whole page reads the selection those controls
# hold: the map, the year track under it, and the tables beside it.

careerORSingleYr = html.Div([
    dbc.RadioItems(id = "careerORSingleYrRadio" + SUFFIX, value = True, className = "btn-group", inputClassName = "btn-check", labelClassName = "btn btn-outline-primary",
        labelCheckedClassName = "active", options = [{"label": "Career", "value": True}, {"label": "Single year", "value": False},
    ])], className = "radio-group")


@callback(
    Output('selectYrRadio' + SUFFIX, 'options'),
    Output('selectYrRadio' + SUFFIX, 'value'),
    [Input('careerORSingleYrRadio' + SUFFIX, 'value')],
    prevent_initial_call=True)
def update_yr_opts(career):
    return(update_yr_options2(career)[0], update_yr_options2(career)[1])


zort = html.Div([dbc.RadioItems(id='selectYrRadio' + SUFFIX,
                      className = "btn-group",
                      labelCheckedClassName = "active",
                      inputClassName = "btn-check",
                      style = {'size':'sm'},
                      labelClassName = "btn btn-outline-primary",
                      # These were hardcoded 2017-2021. The callback below
                      # rebuilds them from the editions table, but it is
                      # prevent_initial_call=True and only fires when the
                      # career/single-year toggle changes, so on first load
                      # the map showed the stale list and stopped at 2021.
                      # Seeding from the same helper fixes the initial render.
                      options = _MAP_YEAR_OPTIONS,
                      value = _MAP_DEFAULT_YEAR)], className = "radio-group year-picker")
zortt = dcc.Dropdown(id='stats2',options={'min':'Minimum (individual)','25':'25% (group)','median':'Median (group)','75':'75% (group)','max':'Maximum (individual)'},value='median')
explain  =  f'''
                    This dashboard section provides a zoomed-out look at the performance metrics that went into the ranking of [the most cited scientists in the world](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3000384&page=69&page=9&page=104&page=7&).
                    You can explore the researchers and institutions that made the cut in each country.

                    #### Global distribution of performance metrics

                    Currently, the world map on the left illustrates the distribution of `median` `H-Index` across countries, derived from the academic performance of the top 2% 
                    researchers throughout their career span (referred to as `Career` data) up to the year `{_MAP_DEFAULT_YEAR}`.
                    
                    <div class="danger">
                    <details>
                    <summary><i data-lucide="help-circle"></i><strong>Career vs single-year</strong></summary>
                    <p>The Elsevier database includes <strong>career-long</strong> and <strong>single-year</strong> records per researcher. For instance, the <strong>career &amp; {_MAP_DEFAULT_YEAR}</strong> selection for H-index shows the score
                    a researcher accumulated up to 2021, while the <strong>single-year & 2021</strong> displays H-index obtained in that year only.</p>
                    </details>
                    </div>
                    <br/>
                    <div class="danger">
                    <details>
                    <summary><i data-lucide="lightbulb"></i><strong>How to use this map</strong></summary>
                    <ul>
                    <li>Switch between <strong>career</strong> and <strong>single year</strong> datasets using the toolbar above the world map and select a year.</li>
                    <li>Use the <strong>slider</strong> below the map to switch between the performance metrics that went into the ranking of the researchers.</li>
                    <li>Use the dropdown to switch between the summary statistics (<strong>min</strong>, <strong>max</strong>, <strong>median</strong>, <strong>25th</strong> and <strong>75th</strong> percentiles). Note that 
                    <strong>min</strong> and <strong>max</strong> metrics corresponds to an individual researcher from the respective country. </li>
                    </ul>
                    </details>
                    </div>
                    <br/>
                    <div class="danger">
                    <details>
                    <summary><i data-lucide="list"></i><strong>What the metric abbreviations mean</strong></summary>
                    <ul>
                    <li><b>h:</b> <a href='https://en.wikipedia.org/wiki/H-index' target='_blank' style='color:blue;'>H-index</a></li>
                    <li><b>nc:</b> Number of citations (#cites)</li>
                    <li><b>hm:</b> <a href='https://ideas.repec.org/a/eee/infome/v2y2008i3p211-216.html' target='_blank' style='color:blue;'>Hm-index</a></li>
                    <li><b>ncs:</b> Number of citations received on single-authored papers (#pprs-s)</li>
                    <li><b>ncsf:</b> Number of citations received on single OR first authored papers (#pprs-sf)</li>
                    <li><b>ncsfl:</b> Number of citations received on single OR first OR last authored papers (#pprs-sfl)</li>
                    <li><b>c:</b> Composite (c) score that determines the ranking</li>
                    </ul>
                    </details>
                    </div>
                    <br/>
                    '''
zart = dls.Ring(dbc.Row([dcc.Markdown(id='cntrylabel', children="", dangerously_allow_html=True),
                    tbl,dcc.Markdown(id='worldtitle',
                    dangerously_allow_html = True,
                    highlight_config  = dict(theme='dark'),
                    children = explain,
                    ),
                    ]),color="#ECAB4C",width=270)


# ============================================================================
# One current author across the whole dashboard
# ----------------------------------------------------------------------------
# Picking someone in any panel should carry to the others: it is the same
# question asked four ways, and retyping the name in each was busywork.
#
# The selection lives in a store rather than being written from one dropdown
# into another. Panels are built on demand, so a callback writing into a
# dropdown that is not mounted yet would fail; seeding the layout at build
# time cannot. The one panel that is always mounted, the trends section, is
# kept in step by the callback below.
# ============================================================================

AUTHOR_PICKERS = [
    "authorOptionsDropdown_single_author",
    "author1OptionsDropdown_author_find_",
    "author1OptionsDropdown_author_vs_author",
    "group1ListDropdown_author_vs_group",
]


@callback(
    Output("spotlight-selection", "data", allow_duplicate=True),
    [Input(picker, "value") for picker in AUTHOR_PICKERS],
    prevent_initial_call=True,
)
def remember_author(*values):
    """Record whichever picker was just changed as the current author."""
    triggered = callback_context.triggered_id
    if triggered not in AUTHOR_PICKERS:
        raise PreventUpdate
    chosen = values[AUTHOR_PICKERS.index(triggered)]
    if not chosen:
        raise PreventUpdate
    return chosen


@callback(
    Output("authorOptionsDropdown_single_author", "value"),
    Input("spotlight-selection", "data"),
    State("authorOptionsDropdown_single_author", "value"),
    prevent_initial_call=True,
)
def sync_trends_author(chosen, current):
    """Keep the always-mounted trends picker on the current author.

    Returning the value it already holds would be a no-op anyway, but
    PreventUpdate says so explicitly and keeps this off the callback graph
    when nothing changed.
    """
    if not chosen or chosen == current:
        raise PreventUpdate
    return chosen


# The instruction that used to sit at the bottom of the right-hand column,
# lifted into a glass card over the map. It says one thing, once, and then
# gets out of the way; leaving it in the column meant it occupied space that
# belongs to the country results for the whole session.
map_hint = html.Div(
    [
        html.Button(
            html.I(**{"data-lucide": "x"}),
            id="map-hint-close", n_clicks=0, className="ev-hint-close",
            title="Dismiss",
        ),
        html.Div(
            [
                html.I(**{"data-lucide": "mouse-pointer-click"}),
                html.Div(
                    [
                        html.Div("Click a place to read it",
                                 className="ev-hint-title"),
                        html.Div(
                            "On Cities, every point is a city and clicking "
                            "one lists the researchers who work there, best "
                            "score first. On Countries, clicking a country "
                            "lists what it contributes. Either way it "
                            "follows the dataset and year selected above.",
                            className="ev-hint-body"),
                    ]
                ),
            ],
            className="ev-hint-row",
        ),
    ],
    id="map-hint",
    className="ev-hint",
)


@callback(
    Output("map-hint", "style"),
    Input("map-hint-close", "n_clicks"),
    Input('glowPicked_glowmap_', 'value'),
    prevent_initial_call=True,
)
def dismiss_map_hint(_close, _clicked):
    """Hide the hint once it has been read, or made redundant.

    Clicking a country is included deliberately: at that point the user has
    done the thing the hint asks for, so the card has nothing left to say.

    This sets an inline style rather than swapping in a class that sets
    opacity: 0. The class was being applied correctly, and pointer-events from
    it took effect, but the computed opacity stayed at 1, so the card went
    inert while still being visible, which looked like a close button that did
    nothing. An inline display:none cannot be out-ranked by a stylesheet rule.
    """
    return {"display": "none"}


offcanvas = html.Div(
    [
        dbc.Offcanvas(
            dcc.Markdown(
                dangerously_allow_html=True,
                children='''
                #### Top 2% researchers

                <div class="ev-byline">Nadia Blostein, Agah Karakuzu, and Nikola Stikov</div>

                ---

                This dashboard provides an intuitive interface to explore top 2% researchers database [(Ioannidis et al. 2019)](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3000384&page=69&page=9&page=104&page=7&), 
                a standardized information on citations, h-index, co-authorship-adjusted hm-index, citations to papers in various authorship positions, and a composite indicator.

                Citation and publication data of the top-ranking authors (based on their respective composite scores) are openly available on the [Elsevier Data Repository](https://elsevier.digitalcommonsdata.com/datasets/btchxktzyw/5).
                
                ---
                This dashboard and the database is generously hosted by [Evidence](https://evidencepub.io). 
                
                Contact us at `info@evidencepub.io` if you are interested in sharing a data application to supplement your research articles. 

                Powered by Plotly Dash and Elasticsearch. 

                Source repository by the [NotebookFactory](https://github.com/Notebook-Factory/twopercenters)
                '''
            ),
            id="offcanvas",
            title="Twopercenters dashboard",
            # Starts closed. zz/spotlight.js opens it once per browser on a
            # first visit and records that it has been seen; after that the
            # More info button is the way back to it. Opening it over the page
            # on every single load, with a backdrop dimming everything behind
            # it, made the dashboard unusable until dismissed.
            is_open=False,
            className="ev-intro",
        ),
    ]
)


@callback(
    Output("offcanvas", "is_open"),
    Input("off", "n_clicks"),
    [State("offcanvas", "is_open")],
)
def toggle_offcanvas(n1, is_open):
    if n1:
        return not is_open
    return is_open

# Served out of assets/ rather than hotlinked from GitHub, so the mark still
# renders if github.com is unreachable from the deployment.
EVIDENCE_LOGO = "/assets/evidence-logo.png"
EVIDENCE_URL = "https://evidencepub.io"
# The mark and the wordmark sit together on the left as one brand lockup,
# rather than being spread apart by justify='around' inside a container that
# CSS was squeezing into the left third of the bar. dark=True so Bootstrap
# picks light foreground colours to go with the dark ground set in style.css.
# One row, three groups, one height. The previous version stacked a wordmark
# over an attribution line inside a Bootstrap grid Row, which made the bar tall
# and ragged and left the right-hand buttons floating against nothing. Here the
# brand is a fixed-height lockup, the actions are a single flex group, and
# every control in the bar is 36px so they share a baseline.
dede = dbc.Navbar(
    dbc.Container(
        [
            html.Div(
                [
                    html.A(html.Img(src=EVIDENCE_LOGO, className="ev-mark"),
                           href="/"),
                    html.Div(
                        [
                            html.A("Twopercenters", href="/",
                                   className="ev-wordmark"),
                            html.Span(
                                [
                                    "developed and hosted by ",
                                    html.A("Evidence", href=EVIDENCE_URL,
                                           target="_blank",
                                           className="ev-attrib-link"),
                                ],
                                className="ev-tagline",
                            ),
                        ],
                        className="ev-brand-text",
                    ),
                ],
                className="ev-brand",
            ),
            html.Div(
                [
                    dbc.Button(
                        [html.I(**{"data-lucide": "search"}),
                         html.Span("Search researchers",
                                   className="ev-search-label"),
                         html.Kbd("⌘K", className="ev-kbd")],
                        id="spotlight-open", className="ev-nav-search",
                        n_clicks=0),
                    html.Span(className="ev-nav-sep"),
                    dbc.Button([html.I(**{"data-lucide": "user"}), "Explore"],
                               id="jump-explore", className="ev-nav-btn",
                               n_clicks=0),
                    dbc.Button([html.I(**{"data-lucide": "trophy"}),
                                "Top 10"],
                               id="jump-top10", className="ev-nav-btn",
                               n_clicks=0),
                    dbc.Button([html.I(**{"data-lucide": "users"}), "Compare"],
                               id="jump-compare", className="ev-nav-btn",
                               n_clicks=0),
                    dbc.Button([html.I(**{"data-lucide": "trending-up"}),
                                "Trends"],
                               id="jump-trends", className="ev-nav-btn",
                               n_clicks=0),
                    html.Span(className="ev-nav-sep"),
                    dbc.Button(id="theme-toggle", n_clicks=0,
                               className="ev-theme-toggle",
                               title="Switch between dark and light"),
                ],
                className="ev-nav-actions",
            ),
        ],
        className="ev-navbar-inner",
        fluid=True,
    ),
    dark=True,
    sticky="top",
)


# Button id -> the section it opens, by item_id rather than by position in
# ACCORDION_SECTIONS. Reordering the sections used to silently repoint these:
# "Compare" returned SECTIONS[0], so once "explore" took first place the
# multi-person icon opened the single-researcher section.
_JUMP_TARGETS = {
    "jump-explore": "explore",
    "jump-top10": "top10",
    "jump-trends": "trends",
    "jump-compare": "compare",
}


@callback(
    Output("accordion", "active_item"),
    Input("jump-explore", "n_clicks"),
    Input("jump-top10", "n_clicks"),
    Input("jump-trends", "n_clicks"),
    Input("jump-compare", "n_clicks"),
    prevent_initial_call=True,
)
def jump_to_section(_explore, _top10, _trends, _compare):
    """Open the section whose navbar button was pressed.

    Which button fired is read from the trigger rather than from the click
    counts, because comparing counts breaks as soon as one button is pressed
    twice in a row.
    """
    target = _JUMP_TARGETS.get(callback_context.triggered_id)
    if target is None:
        raise PreventUpdate
    return target


# Opening the section is not the same as going to it.
#
# "explore" is the section the accordion starts on, so pressing Explore set
# active_item to the value it already held: the callback above returned, Dash
# saw no change, and nothing at all happened on screen. The other two buttons
# did open their section, but left the reader at the top of the page with the
# change happening somewhere below the fold.
#
# Scrolling belongs in the browser rather than in a server callback, and it is
# safe here in a way it was not in the picker: this runs on a click, not on
# every DOM mutation.
dash.clientside_callback(
    """
    function (explore, trends, compare) {
        var trigger = (dash_clientside.callback_context.triggered || [])[0];
        if (!trigger || !trigger.value) { return window.dash_clientside.no_update; }
        var order = {'jump-explore': 0, 'jump-top10': 1, 'jump-trends': 2,
                     'jump-compare': 3};
        var index = order[trigger.prop_id.split('.')[0]];
        if (index === undefined) { return window.dash_clientside.no_update; }

        // After the section has opened, so the header is where it will stay.
        setTimeout(function () {
            var items = document.querySelectorAll('#accordion .accordion-item');
            var item = items[index];
            if (!item) { return; }
            // The toolbar is sticky, so scrolling the header to the top of the
            // viewport would put it underneath.
            var bar = document.querySelector('.ev-toolbar');
            var clearance = (bar ? bar.getBoundingClientRect().height : 0) + 14;
            var top = item.getBoundingClientRect().top + window.scrollY;
            window.scrollTo({top: Math.max(0, top - clearance),
                             behavior: 'smooth'});
        }, 160);
        return '';
    }
    """,
    Output("jump-sink", "children"),
    Input("jump-explore", "n_clicks"),
    Input("jump-top10", "n_clicks"),
    Input("jump-trends", "n_clicks"),
    Input("jump-compare", "n_clicks"),
    prevent_initial_call=True,
)


info_button = dbc.Button("More info", id='off', n_clicks=0,
                    className='ev-info-btn')

def _field(label, control, grow=False):
    """One labelled control in the toolbar.

    The row used to be four bare widgets centred next to each other with no
    labels and no gaps, so it read as one undifferentiated strip and nothing
    said what any of them did. A caption above each control costs one line and
    removes the guessing.
    """
    return html.Div(
        [html.Label(label, className="ev-field-label"), control],
        className="ev-field" + (" ev-field-grow" if grow else ""),
    )


# Dataset and year are one choice made in two parts: which series, then which
# edition of it. Presenting them as two separate labelled controls made the
# user read them as unrelated. They share a single track now, dataset on the
# left, years on the right, with a divider between: the shape of a picker
# rather than of two toolbars that happen to be adjacent.
def _picker(dataset_control, year_control):
    return html.Div(
        [
            html.Div(dataset_control, className="ev-picker-left"),
            html.Span(className="ev-picker-sep"),
            html.Div(year_control, className="ev-picker-right"),
        ],
        className="ev-picker",
    )


row1 = html.Div(
    [
        _field("Dataset and year", _picker(careerORSingleYr, zort), grow=True),
        _field("Statistic", zortt),
        html.Div(info_button, className="ev-toolbar-end"),
    ],
    className="ev-toolbar",
)

# Toolbar over a two-pane body: map on the left, country summary on the right.
# They are cards now with room around them, rather than two grid columns butted
# together against the page.
navigation_row = html.Div(
    [
        row1,
        dbc.Row(
            [
                dbc.Col(html.Div([glow_map(), map_hint],
                                 className="ev-map-pane"),
                        width=8),
                dbc.Col(zart, width=4),
            ],
            className="ev-panes",
        ),
    ],
    className="ev-stage",
)

tabs = [
    dbc.Tabs(
        [   
            # "comparison" on three of four labels is the word they have in
            # common, so it carries no information and only makes the row wide
            # enough to wrap.
            dbc.Tab(label="Author vs author", tab_id="tab-1"),
            dbc.Tab(label="Author vs group", tab_id="tab-2"),
            dbc.Tab(label="Group vs group", tab_id="tab-3"),
        ],
        id="tabs",
        active_tab="tab-1",
    ),
    html.Div(id="content"),
]

@callback(Output("content", "children"), [Input("tabs", "active_tab")],
          State("spotlight-selection", "data"))
def switch_tab(at, picked):
    # Each panel is built on demand, so the current author is handed to it at
    # build time rather than written into its dropdown afterwards: the
    # dropdown does not exist until this returns. Group vs group has no author
    # side, so it takes nothing.
    if at == "tab-1":
        return html.Center(author_vs_author_layout(picked))
    elif at == "tab-2":
        return html.Center(author_vs_group_layout(picked))
    elif at == "tab-3":
        return html.Center(group_vs_group_layout())
    return html.P("This shouldn't ever be displayed...")


@callback(Output("explore-content", "children"),
          Input("accordion", "active_item"),
          State("spotlight-selection", "data"))
def build_explore(active, picked):
    """Build "Find an author" when its section is opened.

    Same on-demand rule as the tabs: the panel is built here rather than at
    import, so a name chosen in the spotlight is handed to it at build time
    instead of a callback writing into a dropdown that does not exist yet.
    """
    if active != ACCORDION_SECTIONS[0][0]:
        raise PreventUpdate
    return html.Center(author_find_layout(picked) if picked
                       else author_find_layout())


# item_id lets the navbar's jump buttons open a section directly. The
# "(toggle)" the titles used to carry is gone: the chevron and the hover state
# say it, and a title that has to explain its own widget is a sign the widget
# is not reading as one.
ACCORDION_SECTIONS = [
    ("explore", "One researcher, explore metrics",
     "Every metric for one researcher, against the field they work in",
     "user"),
    ("top10", "Top 10, by score and by metric",
     "Who leads the selected edition, and which indicator puts them there",
     "trophy"),
    ("trends", "One researcher, year by year",
     "How a single researcher's metrics move across editions",
     "trending-up"),
    ("compare", "Compare researchers, fields and countries",
     "Put two researchers, or a researcher and a group, side by side",
     "users"),
]

# What each section holds. Keyed by item_id for the same reason the jump
# buttons are: the items used to be written out one by one against
# ACCORDION_SECTIONS[0], [1] and [2], so inserting a section silently gave
# three of them somebody else's title.
_SECTION_CONTENT = {
    "explore": lambda: html.Div(id="explore-content"),
    "top10": top10_layout,
    "trends": single_author_layout,
    "compare": lambda: html.Div(tabs),
}


accordion = html.Div(
    dbc.Accordion(
        [
            dbc.AccordionItem(
                [_SECTION_CONTENT[item_id]()],
                title = title,
                item_id = item_id,
                # The section's own accent is keyed off this class rather
                # than off its position. assets/style.css used to colour the
                # sections with :nth-of-type, so inserting Top 10 as the
                # second one handed every section below it the colour of its
                # neighbour while the navbar buttons kept theirs.
                class_name = f'ev-section ev-section-{item_id}',
            )
            for item_id, title, _blurb, _icon in ACCORDION_SECTIONS
        ],
        flush = False,
        id='accordion',
        active_item = ACCORDION_SECTIONS[0][0],
    ),
    id='accordion-anchor',
)

# Clientside callbacks need somewhere to return to; this is that and nothing
# else.
jump_sink = html.Div(id="jump-sink", style={"display": "none"})


def _footer_link(icon, label, href):
    """One labelled link with a Lucide glyph in front of it."""
    return html.A(
        [html.I(**{"data-lucide": icon}), html.Span(label)],
        href=href, target="_blank", className="ev-foot-link",
    )


# A sign-off, not a second masthead: the mark on the left, the links beside it,
# the wordmark bottom-right. Both marks are served from assets/ rather than
# hotlinked, so the footer still renders if evidencepub.io is unreachable from
# the deployment.
footer = html.Footer(
    id='footer',
    className='ev-footer',
    children=[
        html.Div(
            [
                html.A(
                    [
                        # Two files rather than a CSS filter: the mark's body
                        # is one class in the SVG (#394459, the same navy as
                        # the dark page), and a light page needs that piece
                        # white while the coloured leaves stay as they are. A
                        # filter cannot single it out. CSS shows one or the
                        # other per theme.
                        # White body on the dark theme, navy body on the
                        # light one: the body is the same navy as the dark
                        # page, so it vanishes there unless it is swapped.
                        html.Img(src="/assets/evidence-mark-light.svg",
                                 className="ev-foot-mark ev-only-dark",
                                 alt="Evidence"),
                        html.Img(src="/assets/evidence-mark.svg",
                                 className="ev-foot-mark ev-only-light",
                                 alt="Evidence"),
                    ],
                    href="https://evidencepub.io", target="_blank",
                    className="ev-foot-brand",
                ),
                html.Div(
                    [
                        _footer_link("book-open", "Preprint",
                                     "https://journals.plos.org/plosbiology/"
                                     "article?id=10.1371/journal.pbio.3000384"),
                        _footer_link("database", "Elsevier data",
                                     "https://elsevier.digitalcommonsdata.com/"
                                     "datasets/btchxktzyw/5"),
                        _footer_link("code", "Source code",
                                     "https://github.com/Notebook-Factory/twopercenters"),
                        _footer_link("mail", "Contact",
                                     "mailto:info@evidencepub.io"),
                    ],
                    className="ev-foot-links",
                ),
            ],
            className="ev-foot-top",
        ),
        html.Div(
            [
                html.Span("Top 2% most-cited researchers",
                          className="ev-foot-note"),
                html.A(
                    html.Img(src="/assets/evidence-label.svg",
                             className="ev-foot-label", alt="Evidence"),
                    href="https://evidencepub.io", target="_blank",
                ),
            ],
            className="ev-foot-bottom",
        ),
    ],
)


# ============================================================================
# Spotlight search
# ----------------------------------------------------------------------------
# The author typeahead used to live only inside a tab inside a collapsed
# accordion, so the dashboard's main verb was three clicks down. This lifts it
# to a command-palette overlay: Cmd-K / Ctrl-K anywhere, or the Search button
# in the navbar. It reuses get_es_results against the `authors` alias, which is
# the same fuzzy search the in-tab dropdown uses, so a typo still finds the
# author. Picking a result opens the trends section for that author.
# ============================================================================

spotlight = dbc.Modal(
    [
        dbc.ModalBody(
            [
                # A plain text input, not a dcc.Dropdown. The dropdown could
                # not be focused reliably on open (its real <input> is nested
                # and remounts as options arrive), and it draws a form control
                # where Spotlight draws a bare line of text. This is one big
                # borderless field plus a result list underneath, which is the
                # shape people already know.
                dcc.Input(
                    id="spotlight-input",
                    type="text",
                    value="",
                    placeholder="Search researchers…",
                    autoComplete="off",
                    debounce=False,
                    autoFocus=True,
                    className="ev-spotlight-input",
                ),
                html.Div(id="spotlight-results",
                         className="ev-spotlight-results"),
                html.Div(
                    [
                        html.Span("Fuzzy search: misspellings are fine."),
                        html.Span("esc to close", className="ev-spotlight-esc"),
                    ],
                    className="ev-spotlight-hint",
                ),
                # "esc to close" told a reader how to leave but gave them
                # nothing to click, which is a keyboard instruction standing
                # in for a control. Anyone reaching for a mouse, or on a
                # touch screen where there is no esc key at all, was stuck.
                html.Button("\u00d7", id="spotlight-close", n_clicks=0,
                            title="Close", **{"aria-label": "Close search"},
                            className="ev-overlay-close"),
            ],
            className="ev-spotlight-body",
        ),
    ],
    id="spotlight",
    is_open=False,
    centered=False,
    size="lg",
    contentClassName="ev-spotlight",
    backdrop=True,
)

# How many names the overlay offers. Spotlight-style lists are short on
# purpose: a long list is a second search problem.
SPOTLIGHT_LIMIT = 8


@callback(
    Output("spotlight-results", "children"),
    Input("spotlight-input", "value"),
)
def spotlight_results(term):
    """The same fuzzy search the in-tab dropdown runs, as a clickable list."""
    if not term or len(term) < 2:
        return []
    names = es_result_pick(
        get_es_results(term, ['career', 'singleyr'], 'authfull'), 'authfull')
    if not names:
        return html.Div("No researcher by that name.",
                        className="ev-spotlight-empty")
    return [
        html.Button(
            name,
            id={"type": "spotlight-hit", "index": i},
            className="ev-spotlight-hit",
            n_clicks=0,
        )
        for i, name in enumerate(names[:SPOTLIGHT_LIMIT])
    ]


@callback(
    Output("spotlight", "is_open"),
    Input("spotlight-open", "n_clicks"),
    Input("spotlight-close", "n_clicks"),
    Input({"type": "spotlight-hit", "index": ALL}, "n_clicks"),
    State("spotlight", "is_open"),
    prevent_initial_call=True,
)
def toggle_spotlight(_clicks, _close, hits, is_open):
    """Open on the navbar button, close on the X or once a result is picked."""
    triggered = callback_context.triggered_id
    if triggered == "spotlight-open":
        return not is_open
    if triggered == "spotlight-close":
        return False
    if isinstance(triggered, dict) and any(hits or []):
        return False
    raise PreventUpdate


@callback(
    Output("accordion", "active_item", allow_duplicate=True),
    Output("spotlight-selection", "data"),
    Input({"type": "spotlight-hit", "index": ALL}, "n_clicks"),
    State("spotlight-results", "children"),
    prevent_initial_call=True,
)
def spotlight_pick(hits, rendered):
    """Open "Find an author" on the name that was clicked.

    The name is read back out of the rendered button rather than kept in a
    parallel list, so the label the user clicked and the name that is opened
    cannot disagree.
    """
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict) or not any(hits or []):
        raise PreventUpdate
    index = triggered["index"]
    try:
        chosen = rendered[index]["props"]["children"]
    except (TypeError, IndexError, KeyError):
        raise PreventUpdate
    # "Find an author" is its own accordion section now rather than a tab, so
    # this opens the section and no longer selects a tab that is gone.
    return ACCORDION_SECTIONS[0][0], chosen


# The theme switch is clientside for two reasons: it must not wait on a server
# round trip to repaint, and the choice has to survive a reload, which means
# localStorage rather than Dash state. It sets data-theme on <html>; style.css
# defines the light palette against that attribute, so nothing else changes.
dash.clientside_callback(
    """
    function (n) {
        if (!n) { return window.dash_clientside.no_update; }
        var root = document.documentElement;
        var next = root.dataset.theme === 'light' ? 'dark' : 'light';
        root.dataset.theme = next;
        try { window.localStorage.setItem('ev-theme', next); } catch (e) {}
        // Nothing is written back into the button. Its icon is drawn by CSS
        // from data-theme, so there is no DOM for this callback to fight
        // with, which is what made the toggle need several clicks before.
        return window.dash_clientside.no_update;
    }
    """,
    Output("theme-toggle", "title"),
    Input("theme-toggle", "n_clicks"),
    prevent_initial_call=True,
)


# Scrolling is the other half of "bring it into scope": opening a section
# below the fold changes nothing the user can see. Dash cannot scroll, so this
# runs in the browser, after the section has had a moment to expand.
dash.clientside_callback(
    """
    function (compareClicks, trendsClicks, picked) {
        setTimeout(function () {
            var el = document.getElementById('accordion-anchor');
            if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }
        }, 250);
        return window.dash_clientside.no_update;
    }
    """,
    Output("spotlight-hotkey", "data"),
    Input("jump-compare", "n_clicks"),
    Input("jump-trends", "n_clicks"),
    Input("spotlight-selection", "data"),
    prevent_initial_call=True,
)


layout = dbc.Container(fluid = True, children = [
        offcanvas,
        spotlight,
        dcc.Store(id="spotlight-hotkey"),
        dcc.Store(id="spotlight-selection"),
        # What the Explore tab should open on, when something else sends a
        # researcher there. Explore works out an author's available years
        # itself and lands on the earliest, which is right when a name is
        # typed into it and wrong when Top 10 hands it a researcher from a
        # particular edition. Read and cleared by auth_find.
        dcc.Store(id="explore-preset"),
        dede,
        html.Div(navigation_row),
        html.Br(),
        html.Hr(),
        dbc.Row(accordion),
        jump_sink,
        footer
        ], className = 'ev-page ev-shell')
    # dbc.Tooltip("Options selected in this row determine what dataset NC metrics are obtained from.", target = "selectStep1Card", placement = "right"), 
    # dbc.Tooltip("Exclude or include author self citations.", target = "selfCToggle", placement = "right"), 
    # dbc.Tooltip("Author metrics from entire career-span ('Career') or just from year of interest ('Single year').", target = "careerSingleYrRadio", placement = "right"), 
    # dbc.Tooltip("Note: single year data not available for 2018.", target = "selectYrRadioRadio", placement = "right"), 
    # dbc.Tooltip("Go to page on number of citations", target = "nc_button", placement = "right", id = 'nc_button_tt'), 
    # dbc.Tooltip("Go to page on h-index", target = "h_button", placement = "right", id = 'h_button_tt'), 
    # dbc.Tooltip("Go to page on hm-index", target = "hm_button", placement = "right", id = 'hm_button_tt'), 
    # dbc.Tooltip("Go to page on total cites to single authored papers", target = "ncs_button", placement = "right", id = 'ncs_button_tt'), 
    # dbc.Tooltip("Go to page on total cites to single+first authored papers", target = "ncsf_button", placement = "right", id = 'ncsf_button_tt'), 
    # dbc.Tooltip("Go to page on total cites to single+first+last authored papers", target = "ncsfl_button", placement = "right", id = 'ncsfl_button_tt'), 
    # dbc.Tooltip("Go to page on composite score C", target = "c_button", placement = "right", id = 'c_button_tt'), 
