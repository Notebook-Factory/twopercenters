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
from citations_lib.single_author_layout import *
from citations_lib.author_vs_group_layout import *
from citations_lib.group_vs_group_layout import *
from citations_lib.author_vs_author_layout import *
from citations_lib.auth_find import *


# =============== Register page
dash.register_page(__name__, path = '/')
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

tbl  = dash_table.DataTable(
    id = 'instnametable',
    #filter_action="native",
    fixed_rows={'headers': True},
    #filter_options={"placeholder_text": "Filter column..."},
    #style_table={'overflowX': 'auto'},
        style_header={
        'backgroundColor': '#ECAB4C',
        'color': 'white'
    },
    style_data={
        'backgroundColor': 'rgb(50, 50, 50)',
        'color': 'white'
    },
    style_table={'height': '300px', 'overflowY': 'auto','display':'none'},
    style_cell={
        'height': 'auto',
        # all three widths are needed
        #'minWidth': '180px', 
        #'width': '180px', 
        'textAlign': 'left',
        'maxWidth': '0',
        'whiteSpace': 'normal'
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


@callback(
    Output('nav', 'figure',allow_duplicate=True),
    [Input('selectYrRadio' + SUFFIX, 'value'),
    Input('stats2', 'value'),
    Input("careerORSingleYrRadio" + SUFFIX, 'value')],
    prevent_initial_call=True)
def update_world(yr,sts,career):
    if yr is None or sts is None or career is None:
        raise PreventUpdate
    else:
        if career:
            prefix = 'career'
        else:
            prefix = 'singleyr'
        df =  get_world_df(yr,sts,prefix)
        fig = px.choropleth(data_frame=df,
                            locations='code',
                            color=sts,
                            color_continuous_scale="viridis",
                            #range_color=(0, 15000),
                            animation_frame='metric',
                            hover_data=['country','metric_name','metric'])
        fig.update_layout(
                    autosize=True,
                    height = 700,
                    coloraxis_colorbar_thickness=23,
                    coloraxis_colorbar_tickfont=dict(color='white'),
                    coloraxis_colorbar_title=dict(font={"color":'white'}),
                    coloraxis_colorbar_orientation = "h",
                    coloraxis_colorbar_y = -0.1,
                    plot_bgcolor= darkAccent1,
                    paper_bgcolor= darkAccent1,
                    )
        fig.update_layout(geo_bgcolor=darkAccent1,margin={'l':0, 'r':0,'b':0,'t':0})
        fig.update_layout(sliders=[ dict(font = {'color':'white'},bgcolor = '#ECAB4C')
                                   ])
        fig.update_geos(projection=dict(scale = 1), center=dict(lat=30),showframe=False)
    return fig


"""
World map interactions
"""
@callback(
    Output('worldtitle', 'children',allow_duplicate=True),
    Output('instnametable','data'),
    Output('cntrylabel','children'),
    Output('instnametable','style_table'),
    Output("instnametable", "selected_cells"),
    Output("instnametable", "active_cell"),
    Input('nav', 'clickData'),
    Input("careerORSingleYrRadio" + SUFFIX, 'value'),
    Input("selectYrRadio" + SUFFIX, 'value'),
    Input('stats2', 'value'),
    #prevent_initial_call=True
    prevent_initial_call='initial_duplicate' 
    )
def click_on_map_update(val,is_career,yr,sts):
    if val is None:
        raise PreventUpdate
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
    career_all_c = country_researchers(cntry, nm, yr)
    msg = f'<div class="danger"><center><strong>{txt}</strong><br/><strong>{len(career_all_c)}</strong> researchers from <strong>{len(set(get_all_values_by_key(career_all_c,"INSTITUTE")))}</strong> institutions in <strong>{cntry.upper()}</strong><br/> <u>Click on a cell to display respective summaries</u></center></div>'
    return(self_cit,career_all_c, msg, {'height': '400px', 'overflowY': 'auto','display':'block'},[],None)

# The map's opening frame. Was pinned to '2021'; it follows the most recent
# career edition now, so loading a new edition moves it without an edit here.
_MAP_YEAR_OPTIONS, _MAP_DEFAULT_YEAR = update_yr_options2(True)

df =  get_world_df(_MAP_DEFAULT_YEAR,'median','career') 
fig = px.choropleth(data_frame=df,
                        locations='code',
                        color='median',
                        color_continuous_scale="viridis",
                        #range_color=(0, 15000),
                        animation_frame='metric',
                        hover_data=['country','metric_name','metric'])
fig.update_layout(#width=900,
                height = 700,
                autosize = True,
                coloraxis_colorbar_thickness=23,
                coloraxis_colorbar_tickfont=dict(color='white'),
                coloraxis_colorbar_orientation = "h",
                coloraxis_colorbar_y = -0.1,
                coloraxis_colorbar_title=dict(font={"color":'white'}),
                plot_bgcolor= darkAccent1,
                paper_bgcolor= darkAccent1)
fig.update_layout(sliders=[ dict(font = {'color':'white'},bgcolor = '#ECAB4C',
                                 steps = [{'label':'H-index'}, {'label':'#cites'}, {'label':'#pprs'}, {'label':'Hm-index'}, {'label':'#pprs-s'}, {'label':'#pprs-sf'},{'label':'#pprs-sfl'},{'label':'C'}],
                                 )
                            ],
                updatemenus = [dict(bgcolor = '#ECAB4C')])
fig.update_layout(geo_bgcolor=darkAccent1,margin={'l':0, 'r':0,'b':0,'t':0})
fig.update_geos(projection=dict(scale = 1), center=dict(lat=30),showframe=False)

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
    return(update_yr_options2(career)[0],update_yr_options2(career)[1])

kek = dls.Ring(
        dcc.Graph(id="nav",figure = fig),
        color="#ECAB4C",
        #speed_multiplier=2,
        width=270)

#kek = dcc.Graph(id="nav",figure=fig)
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
                    <h3 style='color:#ECAB4C;'> Bird's eye view of the top 2% </h3>

                    ---

                    This dashboard section provides a zommed-out look at the performance metrics that went into the ranking of [the most cited scientists in the world](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3000384&page=69&page=9&page=104&page=7&).
                    You can explore the researchers and institutions that made the cut in each country.

                    #### Global distribution of performance metrics

                    Currently, the world map on the left illustrates the distribution of `median` `H-Index` across countries, derived from the academic performance of the top 2% 
                    researchers throughout their career span (referred to as `Career` data) up to the year `{_MAP_DEFAULT_YEAR}`.
                    
                    <div class="danger">
                    <details>
                    <summary>❓ <strong>Career vs single-year</strong></summary>
                    <p>The Elsevier database includes <strong>career-long</strong> and <strong>single-year</strong> records per researcher. For instance, the <strong>career &amp; {_MAP_DEFAULT_YEAR}</strong> selection for H-index shows the score
                    a researcher accumulated up to 2021, while the <strong>single-year & 2021</strong> displays H-index obtained in that year only.</p>
                    </details>
                    </div>
                    <br/>
                    <div class="danger">
                    <details>
                    <summary>💡 <strong>Click to see interaction tips</strong></summary>
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
                    <summary>🔡 <strong>Click to see metric abbreviations</strong></summary>
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

                    #### Twopercenters per country

                    <div class="danger2">
                    <strong>Click on a country</strong> to take a look at <strong>which institutions and researchers are listed </strong>
                    for a chosen data type and year within that country.
                    </div>
                    '''
zart = dls.Ring(dbc.Row([dcc.Markdown(id='cntrylabel',children="No country selected. Click on a country.",dangerously_allow_html = True),
                    tbl,dcc.Markdown(id='worldtitle',
                    dangerously_allow_html = True,
                    highlight_config  = dict(theme='dark'),
                    children = explain,
                    ),
                    dbc.Row([
                    html.Br(),
                    dbc.Nav([dbc.NavLink('Jump to sections: Comparisons and researcher trends', href="#accordion", external_link=True)])]),
                    ]),color="#ECAB4C",width=270)


offcanvas = html.Div(
    [
        dbc.Offcanvas(
            dcc.Markdown(
                '''
                #### Top 2% researchers
                #### `Nadia Blostein, Agah Karakuzu, and Nikola Stikov`
                ---

                This dashboard provides an intuitive interface to explore top 2% researchers database [(Ioannidis et al. 2019)](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3000384&page=69&page=9&page=104&page=7&), 
                a standardized information on citations, h-index, co-authorship-adjusted hm-index, citations to papers in various authorship positions, and a composite indicator.

                Citation and publication data of the top-ranking authors (based on their respective composite scores) are openly available on the [Elsevier Data Repository](https://elsevier.digitalcommonsdata.com/datasets/btchxktzyw/5).
                
                ---
                This dashboard and the database is generously hosted by [NeuroLibre](https://neurolibre.org). 
                
                Contact us at `info@neurolibre.org` if you are interested in sharing a data application to supplement your research articles. 

                Powered by Plotly Dash and Elasticsearch. 

                Source repository by the [NotebookFactory](https://github.com/Notebook-Factory/twopercenters)
                '''
            ),
            id="offcanvas",
            title="Twopercenters dashboard",
            is_open=True,
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
dede = dbc.Navbar(
    dbc.Container(
        [
            # Brand lockup: mark, wordmark, attribution. One anchor, so the
            # whole thing is a single target back to the top.
            html.A(
                dbc.Row(
                    [
                        dbc.Col(html.Img(src=EVIDENCE_LOGO, height="36px"),
                                width="auto"),
                        dbc.Col(
                            [
                                html.Div("Twopercenters", className="ev-wordmark"),
                                html.Div(
                                    [
                                        "developed and hosted by ",
                                        html.A("Evidence", href=EVIDENCE_URL,
                                               target="_blank",
                                               className="ev-attrib-link"),
                                    ],
                                    className="ev-attrib",
                                ),
                            ],
                            width="auto",
                        ),
                    ],
                    align="center",
                    className="g-2 flex-nowrap",
                ),
                href="/",
                className="ev-brand",
            ),
            # Right side: one button per collapsible section below, plus the
            # search. These exist because the sections were being missed: the
            # accordion headers were the only way in, and people did not read
            # them as controls.
            html.Div(
                [
                    dbc.Button("Search", id="spotlight-open",
                               className="ev-nav-search", n_clicks=0),
                    dbc.Button("◑", id="theme-toggle", n_clicks=0,
                               className="ev-theme-toggle",
                               title="Switch between dark and light"),
                    dbc.Button("Compare", id="jump-compare",
                               className="ev-nav-btn", n_clicks=0),
                    dbc.Button("Trends", id="jump-trends",
                               className="ev-nav-btn", n_clicks=0),
                ],
                className="ev-nav-actions",
            ),
        ],
        className="d-flex justify-content-between align-items-center",
        fluid=True,
    ),
    dark=True,
    sticky="top",
)


@callback(
    Output("accordion", "active_item"),
    Input("jump-compare", "n_clicks"),
    Input("jump-trends", "n_clicks"),
    prevent_initial_call=True,
)
def jump_to_section(_compare, _trends):
    """Open the section whose navbar button was pressed.

    Which button fired is read from the trigger rather than from the click
    counts, because comparing counts breaks as soon as one button is pressed
    twice in a row.
    """
    triggered = callback_context.triggered_id
    if triggered == "jump-compare":
        return ACCORDION_SECTIONS[0][0]
    if triggered == "jump-trends":
        return ACCORDION_SECTIONS[1][0]
    raise PreventUpdate


info_button = dbc.Button("More info", id='off', n_clicks=0,
                    className='ev-info-btn')

row1 = dbc.Row([
            dbc.Col(html.Center(careerORSingleYr), width = 2), 
            dbc.Col(html.Center(zort), width = 4),
            dbc.Col(html.Center(zortt),width = 2),
            dbc.Col(info_button, width='auto', className='d-flex align-items-center')
            # dbc.Col(dcc.Markdown(id='cntrylabel',children="`No country selected`",dangerously_allow_html = True),width=4)
            ],justify="start",align="center",style={'margin-top':'10px'})

navigation_row =  dbc.Row([
        dbc.Col([dbc.Row(row1),dbc.Row([dbc.Col(html.Div(kek),width=8),dbc.Col(zart,width=4)])]),
    ],justify='start', align='center')

tabs = [
    dbc.Tabs(
        [   
            dbc.Tab(label="Find an author", tab_id="tab-0"),
            dbc.Tab(label="Author vs author comparison", tab_id="tab-1"),
            dbc.Tab(label="Author vs group comparison", tab_id="tab-2"),
            dbc.Tab(label="Group vs group comparison", tab_id="tab-3"),
        ],
        id="tabs",
        active_tab="tab-0",
    ),
    html.Div(id="content"),
]

@callback(Output("content", "children"), [Input("tabs", "active_tab")],
          State("spotlight-selection", "data"))
def switch_tab(at, picked):
    if at == "tab-1":
        return html.Center(author_vs_author_layout())
    elif at == "tab-2":
        return html.Center(author_vs_group_layout())
    elif at == "tab-3":
        return html.Center(group_vs_group_layout())
    elif at == 'tab-0':
        # The tab is built on demand, so a name chosen in the spotlight is
        # handed over by seeding the layout rather than by a callback writing
        # into a dropdown that does not exist until this returns.
        return html.Center(author_find_layout(picked)
                           if picked else author_find_layout())
    return html.P("This shouldn't ever be displayed...")


# item_id lets the navbar's jump buttons open a section directly. The
# "(toggle)" the titles used to carry is gone: the chevron and the hover state
# say it, and a title that has to explain its own widget is a sign the widget
# is not reading as one.
ACCORDION_SECTIONS = [
    ("compare", "Taking a closer look",
     "Compare researchers, fields and countries"),
    ("trends", "Researcher trends",
     "How a researcher's metrics change over the years"),
]

accordion = html.Div(
    dbc.Accordion(
        [
            dbc.AccordionItem(
                [
                    html.Div(tabs),
                ],
                title = ACCORDION_SECTIONS[0][1],
                item_id = ACCORDION_SECTIONS[0][0],
            ),
            dbc.AccordionItem(
                [
                    single_author_layout(),
                ],
                title = ACCORDION_SECTIONS[1][1],
                item_id = ACCORDION_SECTIONS[1][0],
            )
        ],
        flush = False,
        id='accordion',
        active_item = ACCORDION_SECTIONS[0][0],
    ),
    id='accordion-anchor',
)


ttt = dcc.Markdown('''
                    | [Source Code](https://github.com/Notebook-Factory/twopercenters) | [NoteBook Factory](https://github.com/Notebook-Factory) | [Twitter](https://twitter.com/NeuroLibre) | 
                    ''')
footer = html.Footer(id='footer',
                     children = [
                         html.Hr(),
                         html.Br(),
                         html.Center(html.H3('NeuroLibre DB')),
                         # Was 150px and dominated the footer. The footer is
                         # a sign-off, not a second masthead.
                         html.Center(html.Img(src="https://github.com/neurolibre/brand/blob/main/png/dashboards.png?raw=true", height="72px",
                                              style={'opacity': '0.85'})),
                         html.Center(html.H5('info@neurolibre.org',
                                             style={'marginTop': '12px'})),
                         html.Br(),
                         html.Center(ttt)
                     ])


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
    Input({"type": "spotlight-hit", "index": ALL}, "n_clicks"),
    State("spotlight", "is_open"),
    prevent_initial_call=True,
)
def toggle_spotlight(_clicks, hits, is_open):
    """Open on the navbar button, close once a result has been clicked."""
    triggered = callback_context.triggered_id
    if triggered == "spotlight-open":
        return not is_open
    if isinstance(triggered, dict) and any(hits or []):
        return False
    raise PreventUpdate


@callback(
    Output("accordion", "active_item", allow_duplicate=True),
    Output("tabs", "active_tab"),
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
    return ACCORDION_SECTIONS[0][0], "tab-0", chosen


# The theme switch is clientside for two reasons: it must not wait on a server
# round trip to repaint, and the choice has to survive a reload, which means
# localStorage rather than Dash state. It sets data-theme on <html>; style.css
# defines the light palette against that attribute, so nothing else changes.
dash.clientside_callback(
    """
    function (n) {
        var root = document.documentElement;
        if (n) {
            var next = root.dataset.theme === 'light' ? 'dark' : 'light';
            root.dataset.theme = next;
            try { window.localStorage.setItem('ev-theme', next); } catch (e) {}
        }
        return root.dataset.theme === 'light' ? '◐' : '◑';
    }
    """,
    Output("theme-toggle", "children"),
    Input("theme-toggle", "n_clicks"),
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
        dede,
        html.Div(navigation_row),
        html.Br(),
        html.Hr(),
        dbc.Row(accordion),
        footer
        ], className = 'ev-page')
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
