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
from dash import html, dcc, callback, dash_table #, Input, Output
from dash.dependencies import Input, Output, State
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

darkAccent1 = '#2C2C2C' # dark gray
darkAccent2 = '#5b5959' # pale gray
darkAccent3 = '#CFCFCF' # almost white
lightAccent1 = '#ECAB4C' # ocre
highlight1 = 'lightsteelblue'
highlight2 = 'cornflowerblue'
theme =  {'dark': True, 'detail': lightAccent1, 'primary': darkAccent1, 'secondary': lightAccent1}

g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
g2c = [highlight2, darkAccent3] # bar plot bar 3
bgc = darkAccent1 # bar plot background

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
            results = get_es_results(selection,prefix,'authfull')
            if results is not None:
                data = es_result_pick(results, 'data', None)
                data  = data[f'{prefix}_{yr}']
                self_cit = f'''
                ---
                ##### 🔸 Summary for **{selection.split(',')[0]}** {txt} {yr}
                - `Number of articles published:` **{int(data['np'])}**
                - `Number of citations:` **{int(data['nc'])}**
                - `H-index:` **{int(data['h'])}**
                - `Self citation ratio:` **{np.round(data['self%']*100,2)}%**
                '''
        elif sel_type == 'INSTITUTE':
            data = get_es_aggregate('inst_name',selection,prefix)
            data = data[f'{prefix}_{yr}']
            self_cit = f'''
                ---
                ##### 🔸 Summary ({sts}) for **{selection}** {txt} {yr}
                - `Number of articles published:` **{int(data['np'][st_idx])}**
                - `Number of citations:` **{int(data['nc'][st_idx])}**
                - `H-index:` **{int(data['h'][st_idx])}**
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
    dbc.Row([dbc.Col(dbc.Collapse(dbc.Container(fluid = True, children = [author_vs_author_layout()], style = {'backgroundColor':darkAccent1}), 
        id = "collapse_author_vs_author", is_open = False))], className="mt-3"),
    dbc.Row([dbc.Col(dbc.Collapse(dbc.Container(fluid = True, children = [author_vs_group_layout()], style = {'backgroundColor':darkAccent1}), 
         id = "collapse_author_vs_group", is_open = False))], className="mt-3"),
    dbc.Row([dbc.Col(dbc.Collapse(dbc.Container(fluid = True, children = [group_vs_group_layout()], style = {'backgroundColor':darkAccent1}), 
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
        print('Loading...')
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
                ##### 🔸 Summary statistics ({sts}) for **{cntry.upper()}**
                - `Number of articles published:` **{int(data[f'{cr}_{yr}']['np'][st_idx])}**
                - `Number of citations:` **{int(data[f'{cr}_{yr}']['nc'][st_idx])}**
                - `H-index:` **{int(data[f'{cr}_{yr}']['h'][st_idx])}**
                - `Self citation ratio:` **{np.round(data[f'{cr}_{yr}']['self%'][st_idx]*100,2)}%**
               '''
    query = { "query": { "term": {"cntry":cntry} }, "_source": ['authfull','inst_name','years'] }
    if is_career: 
        nm = 'career'
        txt = f"Career-long up to {yr}"
    else:
        nm = 'singleyr'
        txt = f"Single-year data in {yr}"
    
    cur_data = []
    for total_pages, page_counter, page_items, page_data in es_scroll(nm, query, page_size=page_size):
         cur_data.append(page_data['hits']['hits'])
    career_all_c = [{'INSTITUTE':d['_source']['inst_name'],'RESEARCHER':d['_source']['authfull']}
                        for tmp in cur_data
                        for d in tmp
                        if yr in d['_source']['years']]
    #print(career_all_c)
    msg = f'<div class="danger"><center><strong>{txt}</strong><br/><strong>{len(career_all_c)}</strong> researchers from <strong>{len(set(get_all_values_by_key(career_all_c,"INSTITUTE")))}</strong> institutions in <strong>{cntry.upper()}</strong><br/> <u>Click on a cell to display respective summaries</u></center></div>'
    return(self_cit,career_all_c, msg, {'height': '400px', 'overflowY': 'auto','display':'block'},[],None)

df =  get_world_df('2021','median','career') 
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
                            ])
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
                      options = [{"label": "2017", "value": '2017', 'disabled': False}, {"label": "2018", "value": '2018', 'disabled': False}, 
            {"label": "2019", "value": '2019', 'disabled': False}, {"label": "2020", "value": '2020', 'disabled': False}, {"label": "2021", "value": '2021', 'disabled': False}],value='2021')], className = "radio-group")
zortt = dcc.Dropdown(id='stats2',options={'min':'Minimum (individual)','25':'25% (group)','median':'Median (group)','75':'75% (group)','max':'Maximum (individual)'},value='median')
explain  =  '''
                    <h2 style='color:#ECAB4C;'> 🟠 Bird's eye view of the top 2% </h2>

                    ---

                    This dashboard section provides a zommed-out look at the performance metrics that went into the ranking of [the most cited scientists in the world](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3000384&page=69&page=9&page=104&page=7&).
                    You can explore the researchers and institutions that made the cut in each country.

                    #### Global distribution of performance metrics

                    👈 Currently, the world map on the left illustrates the distribution of `median` `H-Index` across countries, derived from the academic performance of the top 2% 
                    researchers throughout their career span (referred to as `Career` data) up to the year `2021`.
                    
                    <div class="danger">
                    <details>
                    <summary>❓ <strong>Career vs single-year</strong></summary>
                    <p>The Elsevier database includes <strong>career-long</strong> and <strong>single-year</strong> records per researcher. For instance, the <strong>career & 2021</strong> selection for H-index shows the score
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
                    <li><b>np:</b> Number of papers published (#pprs)</li>
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
zart = dls.Ring(dbc.Row([dcc.Markdown(id='cntrylabel',children="`No country selected, displaying instructions.`",dangerously_allow_html = True),
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
                #### `Nadia Blostein, Agah Karakuzu, John P. Ioannidis, and Nikola Stikov`
                ---
                
                This dashboard provides an intuitive interface to explore top 2% researchers database [(Ioannidis et al. 2019)](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3000384&page=69&page=9&page=104&page=7&), 
                a standardized information on citations, h-index, co-authorship-adjusted hm-index, citations to papers in various authorship positions, and a composite indicator.

                Citation and publication data of the top-ranking authors (based on their respective composite scores) are openly available on the [Elsevier Data Repository](https://elsevier.digitalcommonsdata.com/datasets/btchxktzyw/5).

                This dashboard and the database is generously hosted by [NeuroLibre](https://neurolibre.org). 
                
                Contact us at `info@neurolibre.org` if you are interested in sharing a data application to supplement your research articles. 

                Powered by Plotly Dash and Elasticsearch. 

                Source repository by the [NotebookFactory](https://github.com/Notebook-Factory/twopercenters)
                '''
            ),
            id="offcanvas",
            title="Twopercenters dashboard",
            is_open=False,
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

PLOTLY_LOGO = "https://github.com/neurolibre/brand/blob/main/png/neurolibre-icon-red.png?raw=true"
dede = dbc.Navbar(
    dbc.Container(
        [
                # Use row and col to control vertical alignment of logo / brand
                dbc.Row(
                    [
                        dbc.Col(html.Img(src=PLOTLY_LOGO, height="30px")),
                        dbc.Col(dbc.NavbarBrand("Twopercenters dashboard by NeuroLibre")),
                    ],
                    align='center',
                    justify='around'
                ),
            dbc.NavbarToggler(id="navbar-toggler", n_clicks=0),
        ]
    ),
    color="gainsboro"
)

info_button = dbc.Button("About the dataset (Ioannidis et al. 2019) and dashboard", id='off',  n_clicks=0,
                    className='lel2')

row1 = dbc.Row([
            dbc.Col(html.Center(careerORSingleYr), width = 2), 
            dbc.Col(html.Center(zort), width = 4),
            dbc.Col(html.Center(zortt),width = 2),
            dbc.Col(info_button,width='auto')
            # dbc.Col(dcc.Markdown(id='cntrylabel',children="`No country selected`",dangerously_allow_html = True),width=4)
            ],justify="start",align="center",style={'margin-top':'10px'})

navigation_row =  dbc.Row([
        dbc.Col([dbc.Row(row1),dbc.Row([dbc.Col(html.Div(kek),width=8),dbc.Col(zart,width=4)])]),
    ],justify='start', align='center')

tabs = [
    dbc.Tabs(
        [
            dbc.Tab(label="🔸 Author vs author comparison", tab_id="tab-1"),
            dbc.Tab(label="🔸 Author vs group comparison", tab_id="tab-2"),
            dbc.Tab(label="🔸 Group vs group comparison", tab_id="tab-3"),
        ],
        id="tabs",
        active_tab="tab-1",
    ),
    html.Div(id="content"),
]

@callback(Output("content", "children"), [Input("tabs", "active_tab")])
def switch_tab(at):
    if at == "tab-1":
        return html.Center(author_vs_author_layout())
    elif at == "tab-2":
        return author_vs_group_layout()
    elif at == "tab-3":
        return group_vs_group_layout()
    return html.P("This shouldn't ever be displayed...")


accordion = html.Div(
    dbc.Accordion(
        [
            dbc.AccordionItem(
                [
                    html.Div(tabs),
                ],
                title = "🟠 Taking a closer look: Comparing researchers, fields, and countries (toggle)",
            ),
            dbc.AccordionItem(
                [
                    single_author_layout(),
                ],
                title="🟠 Researcher trends: How metrics change for a researcher over the years (toggle)",
            )
        ],
        flush = False,
        id='accordion'
    )
)


ttt = dcc.Markdown('''
                    | [Source Code](https://github.com/Notebook-Factory/twopercenters) | [NoteBook Factory](https://github.com/Notebook-Factory) | [Twitter](https://twitter.com/NeuroLibre) | 
                    ''')
footer = html.Footer(id='footer',
                     children = [
                         html.Hr(),
                         html.Br(),
                         html.Center(html.H3('NeuroLibre DB')),
                         html.Center(html.Img(src="https://github.com/neurolibre/brand/blob/main/png/dashboards.png?raw=true", height="150px")),
                         html.Center(html.H4('info@neurolibre.org')),
                         html.Br(),
                         html.Center(ttt)
                     ])


layout = dbc.Container(fluid = True, children = [
        offcanvas,
        dede,
        html.Div(navigation_row),
        html.Br(),
        html.Hr(),
        dbc.Row(accordion),
        footer
        ], style = {'backgroundColor':darkAccent1})
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
