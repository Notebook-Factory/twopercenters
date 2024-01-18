# ========================================================================================== 
# ========================================================================================== 
# IMPORT LIBRARIES
# ========================================================================================== 
# ========================================================================================== 

# =============== misc libs & modules
import numpy as np
import math
import pickle

# =============== Plotly libs & modules
import plotly.graph_objects as go

# =============== Plotly Dash libraries
import dash
from dash import html, dcc, callback #, Input, Output
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq

# =============== Custom lib
from citations_lib.create_fig_helper_functions import *
from citations_lib.utils import *
from citations_lib.single_author_layout import *
from citations_lib.author_vs_group_layout import *
from citations_lib.group_vs_group_layout import *
from citations_lib.author_vs_author_layout import *
#from citations_lib.metric_tab_layout import *

# =============== Register page
dash.register_page(__name__, path = '/')

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


# ========================================================================================== 
# ========================================================================================== 
# Row: Single author
# ========================================================================================== 
# ========================================================================================== 
single_author_row = html.Div([
    dbc.Row(dbc.Button("Find yourself in the database!", id = "collapse_btn_single_author", class_name = 'd-grid gap-2 col-3 mx-auto',
        style={"color": lightAccent1, 'font-size':'17px', "fontWeight": "bold", "border-color": lightAccent1,"border-radius":"30px", "border-width":"2px", "background-image": "linear-gradient(to bottom, #2C2C2C, #5b5959)"},
        n_clicks = 0, color = darkAccent1),
    justify="center"),
    dbc.Row([dbc.Col(dbc.Collapse(dbc.Container(fluid = True, children = [single_author_layout()], style = {'backgroundColor':darkAccent1}), 
        id = "collapse_single_author", is_open = False))], className="mt-3")])
@callback(
    Output("collapse_single_author", "is_open"),
    Input("collapse_btn_single_author", "n_clicks"),
    State("collapse_single_author", "is_open"))
def toggle(n, is_open):
    if n: return not is_open
    return is_open

layout = html.Div([dbc.Container(fluid = True, children = [single_author_row])])

# # ========================================================================================== 
# # ========================================================================================== 
# # Row: Author vs author, group vs group, author vs group
# # ========================================================================================== 
# # ========================================================================================== 

compare_row = html.Div([
    dbc.Row([
        dbc.Col([html.Center(dbc.Button("Compare author to author", className="me-2", id = "collapse_btn_author_vs_author",
            style={"color": lightAccent1, 'font-size':'17px', "fontWeight": "bold", "border-color": lightAccent1,"border-radius":"30px", "border-width":"2px", "background-image": "linear-gradient(to bottom, #2C2C2C, #5b5959)"},
            n_clicks = 0, color = darkAccent1))], width = 3),
        dbc.Col([html.Center(dbc.Button("Compare group to group", className="me-2", id = "collapse_btn_group_vs_group",
            style={"color": lightAccent1, 'font-size':'17px', "fontWeight": "bold", "border-color": lightAccent1,"border-radius":"30px", "border-width":"2px", "background-image": "linear-gradient(to bottom, #2C2C2C, #5b5959)"},
            n_clicks = 0, color = darkAccent1))], width = 3),
        dbc.Col([html.Center(dbc.Button("Compare author to group", className="me-2", id = "collapse_btn_author_vs_group",
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
    Output("collapse_author_vs_author", "is_open"),
    Input("collapse_btn_author_vs_author", "n_clicks"),
    State("collapse_author_vs_author", "is_open"))
def toggle(n, is_open):
    if n: return not is_open
    return is_open
@callback(
    Output("collapse_author_vs_group", "is_open"),
    Input("collapse_btn_author_vs_group", "n_clicks"),
    State("collapse_author_vs_group", "is_open"))
def toggle(n, is_open):
    if n: return not is_open
    return is_open
@callback(
    Output("collapse_group_vs_group", "is_open"),
    Input("collapse_btn_group_vs_group", "n_clicks"),
    State("collapse_group_vs_group", "is_open"))
def toggle(n, is_open):
    if n: return not is_open
    return is_open
# @callback(
#     Output("collapse_author_vs_author", "is_open"), Output("collapse_author_vs_group", "is_open"), Output("collapse_group_vs_group", "is_open"),
#     Output("collapse_btn_author_vs_author", "n_clicks"),Output("collapse_btn_author_vs_group", "n_clicks"),Output("collapse_btn_group_vs_group", "n_clicks"),
#     Input("collapse_btn_author_vs_author", "n_clicks"),Input("collapse_btn_author_vs_group", "n_clicks"),Input("collapse_btn_group_vs_group", "n_clicks"),
#     State("collapse_author_vs_author", "is_open"),State("collapse_author_vs_group", "is_open"),State("collapse_group_vs_group", "is_open"))
# def toggle(n1, n2, n3, is_open_1, is_open_2, is_open_3):
#     if n1: return(True, False, False, 0, 0, 0) if is_open_1 == False else (False, False, False, 0, 0, 0)
#     elif n2: return(False, True, False, 0, 0, 0) if is_open_2 == False else (False, False, False, 0, 0, 0)
#     elif n3: return(False, False, True, 0, 0, 0) if is_open_3 == False else (False, False, False, 0, 0, 0)
#     else: return(is_open_1, is_open_2, is_open_3, 0, 0, 0)

# # ========================================================================================== 
# # ========================================================================================== 
# # Compare C metrics
# # ========================================================================================== 
# # ========================================================================================== 

# tabContent_nc = get_metric_tab_layout(CURR_METRIC = 'nc', CURR_TITLE = 'Number of citations', DEFAULT_CAREER = True, DEFAULT_YR = 3)
# tabContent_h = get_metric_tab_layout(CURR_METRIC = 'h', CURR_TITLE = 'H-index')
# tabContent_hm = get_metric_tab_layout(CURR_METRIC = 'hm', CURR_TITLE = 'Hm-index')
# tabContent_ncs = get_metric_tab_layout(CURR_METRIC = 'ncs', CURR_TITLE = 'Number of citations to single authored papers')
# tabContent_ncsf = get_metric_tab_layout(CURR_METRIC = 'ncsf', CURR_TITLE = 'Number of citations to single and first authored papers')
# tabContent_ncsfl = get_metric_tab_layout(CURR_METRIC = 'ncsfl', CURR_TITLE = 'Number of citations to single, first and last authored papers')
# tabContent_c = get_metric_tab_layout(CURR_METRIC = 'c', CURR_TITLE = 'Composite score c')
# tabs = html.Div([
#     dbc.Tabs(
#         [dbc.Tab(tabContent_nc, label = "Number of citations",active_tab_class_name = 'custom-metrics-tab-active', className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         dbc.Tab(tabContent_h, label = "H-index", active_tab_class_name = 'custom-metrics-tab-active', className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         dbc.Tab(tabContent_hm, label = "Hm-index", active_tab_class_name = 'custom-metrics-tab-active', className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         dbc.Tab(tabContent_ncs, label = "Number of  citations to single authored papers", active_tab_class_name = 'custom-metrics-tab-active', className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         dbc.Tab(tabContent_ncsf, label = "Number of  citations to single and first authored papers", active_tab_class_name = 'custom-metrics-tab-active', className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         dbc.Tab(tabContent_ncsfl, label = "Number of  citations to single, first and last authored papers", active_tab_class_name = 'custom-metrics-tab-active', className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         dbc.Tab(tabContent_c, label = "Composite score C", active_tab_class_name = 'custom-metrics-tab-active', className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1})
#         ], id = "card-tabs", className='custom-tabs'),
#     dbc.Container(id = 'card-content-compare_c_metrics_row')])
#layout = html.Div([dbc.Container(fluid = True, children = [tabs])])

# compare_c_metrics_row = dbc.Row([html.Center([
#     dbc.Button("Explore metrics input into composite score C", id = "collapse-button-compare_c_metrics_row", class_name = 'd-grid gap-2 col-4 mx-auto',
#         style={"color": lightAccent1, 'font-size':'17px', "fontWeight": "bold", "border-color": lightAccent1,"border-radius":"30px", "border-width":"2px", "background-image": "linear-gradient(to bottom, #2C2C2C, #5b5959)"},
#         n_clicks = 0, color = darkAccent1),
#     dbc.Collapse(
#         dbc.Container(fluid = True, children = [tabs]
#         , style = {'backgroundColor':darkAccent1}), 
#         id = "collapse-compare_c_metrics_row", 
#         is_open = False, 
#     )])])
# @callback(
#     Output("collapse-compare_c_metrics_row", "is_open"), 
#     [Input("collapse-button-compare_c_metrics_row", "n_clicks")], 
#     [State("collapse-compare_c_metrics_row", "is_open")])
# def toggle_collapse(n, is_open):
#     if n: return not is_open
#     return is_open

# # ========================================================================================== 
# # ========================================================================================== 
# # Compare miscellaneous metrics
# # ========================================================================================== 
# # ========================================================================================== 

# tabContent_np = get_metric_tab_layout(CURR_METRIC = 'np', CURR_TITLE = 'Number of papers (NP)', DEFAULT_CAREER = True, DEFAULT_YR = 3)
# tabContent_nps = get_metric_tab_layout(CURR_METRIC = 'nps', CURR_TITLE = 'Number of single authored papers (NPS)')
# tabContent_cpsf = get_metric_tab_layout(CURR_METRIC = 'cpsf', CURR_TITLE = 'Number of single and first authored papers (CPSF)')
# tabContent_npsfl = get_metric_tab_layout(CURR_METRIC = 'npsfl', CURR_TITLE = 'Number of single, first and last authored papers (NPSFL)')
# tabContent_npciting = get_metric_tab_layout(CURR_METRIC = 'npciting', CURR_TITLE = 'Number of distinct citing papers (NPciting)')
# tabContent_cprat = get_metric_tab_layout(CURR_METRIC = 'cprat', CURR_TITLE = 'Ratio of total citations to distinct citing papers (CPRAT)')
# #tabContent_npCited = get_metric_tab_layout(CURR_METRIC = 'np cited', CURR_TITLE = 'Number of papers that have been cited at least once (NP cited)')
# tabContent_selfP = get_metric_tab_layout(CURR_METRIC = 'self%', CURR_TITLE = 'Self-citation percentage')

# tabs_misc_metrics_row = html.Div([
#     dbc.Tabs(
#         [dbc.Tab(tabContent_np, label = "Number of papers", tab_class_name = 'custom-metrics-tab', active_tab_class_name = 'custom-metrics-tab-active', label_style = {'font-size':16}),
#             #className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         dbc.Tab(tabContent_nps, label = "Number of single authored papers", tab_class_name = 'custom-metrics-tab', active_tab_class_name = 'custom-metrics-tab-active', label_style = {'font-size':16}),
#             #className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         dbc.Tab(tabContent_cpsf, label = "Number of single and first authored papers", tab_class_name = 'custom-metrics-tab', active_tab_class_name = 'custom-metrics-tab-active', label_style = {'font-size':16}),
#             #className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}), 
#         dbc.Tab(tabContent_npsfl, label = "Number of single, first and last authored papers", tab_class_name = 'custom-metrics-tab', active_tab_class_name = 'custom-metrics-tab-active', label_style = {'font-size':16}),
#             #className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}), 
#         dbc.Tab(tabContent_npciting, label = "Number of distinct citing papers", tab_class_name = 'custom-metrics-tab', active_tab_class_name = 'custom-metrics-tab-active', label_style = {'font-size':16}),
#             #className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         dbc.Tab(tabContent_cprat, label = "Ratio of total citations to distinct citing papers", tab_class_name = 'custom-metrics-tab', active_tab_class_name = 'custom-metrics-tab-active', label_style = {'font-size':16}),
#             #className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         #dbc.Tab(tabContent_npCited, label = "Number of papers that have been cited at least once (NP cited)", label_style = {"color": lightAccent1}), 
#         dbc.Tab(tabContent_selfP, label = "Self-citation percentage", tab_class_name = 'custom-metrics-tab', active_tab_class_name = 'custom-metrics-tab-active', label_style = {'font-size':16}),
#             #className = 'custom-metrics-tab-active',label_style = {"color": darkAccent3, 'font-size':16}, active_label_style = {"color": highlight1}),
#         ], id = "card-tabs-misc_metrics_row", className='custom-tabs'), 
#     dbc.Container(id = 'card-content-misc_metrics_row')])

# compare_misc_metrics_row = dbc.Row([html.Center([
#     dbc.Button("Explore other metrics", id = "collapse-button-misc_metrics_row", class_name = 'd-grid gap-2 col-3 mx-auto',
#         style={"color": lightAccent1, 'font-size':'17px', "fontWeight": "bold", "border-color": lightAccent1,"border-radius":"30px", "border-width":"2px", "background-image": "linear-gradient(to bottom, #2C2C2C, #5b5959)"},
#         n_clicks = 0, color = darkAccent1),
#     dbc.Collapse(
#         dbc.Container(fluid = True, children = [tabs_misc_metrics_row]
#         , style = {'backgroundColor':darkAccent1}), 
#         id = "collapse-misc_metrics_row", 
#         is_open = False, 
#     )])])
# @callback(
#     Output("collapse-misc_metrics_row", "is_open"), 
#     [Input("collapse-button-misc_metrics_row", "n_clicks")], 
#     [State("collapse-misc_metrics_row", "is_open")], 
# )
# def toggle_collapse(n, is_open):
#     if n: return not is_open
#     return is_open

# # ========================================================================================== 
# # ========================================================================================== 
# # Layout
# # ========================================================================================== 
# # ========================================================================================== 

info  = pd.read_json('cumulative_summary.json')
#N_authors = daq.LEDDisplay(label = {"label":'Number of authors', "style":{"color":darkAccent2, "font-size":"16px"}}, value = int(info['total']), backgroundColor = darkAccent1, color = darkAccent2, size = 40)

layout = html.Div([
    # dcc.Loading(type="circle"),
    html.Div(
        children = [
            html.Img(src = 'assets/neurolibre_logo.png', className = "header-logo"), 
            #html.H1("Science-wide author databases of standardized citation indicators", className = "header-title", style = {"text-shadow": "1px 1px 1px #5b5959"}), # From Spreadsheet to Figure: Interactive Author-Wide Citation Indicators 
            html.H1("Author-wide citation indicators", className = "header-title", style = {"text-shadow": "1px 1px 1px #5b5959"}), # From Spreadsheet to Figure: Interactive Author-Wide Citation Indicators 
            #html.P("John P.A. Ioannidis et al.", className = "header-description", ), 
            html.P("Jeroen Baas, Richard Klavans, Kevin Boyack, John P.A. Ioannidis", className = "header-description"),
            html.P("3 articles (2016, 2019, 2020)", className = "header-description"),
            html.P("5 dataset versions (2017, 2019, 2020, 2021, 2021)", className = "header-description"),
            #html.P("Dashboard: Nadia Blostein, Agâh Karakuzu, Nikola Stikov", className = "header-description"), 
            ], style = {'background-image':"linear-gradient(to bottom, #2C2C2C, #5b5959)",'display': 'flex','flex-direction':'column','height':'280px', 'justify-content':'center'},
            className = "header"),
    dbc.Container([
        html.Br(),
        html.Center('About the data', style={"font-weight": "bold", 'font-size':23, 'color': lightAccent1, "text-shadow": "1px 1px 1px #5b5959"}),
        html.Br(),
        dbc.Row(dbc.Col(dcc.Markdown('''
            6 citation metrics were used to compute a composite score (C) for authors indexed in the Scopus publication database.
            Citation and publication data of the top-ranking authors (based on their respective composite scores) are openly available on the [Elsevier Data Repository](https://elsevier.digitalcommonsdata.com/datasets/btchxktzyw/5). A couple important specifications:  
            * **Career-long** data in a given year refers to author-specific metrics computed from the beginning of their career until that given year. This data is available for the years of 2017, 2018, 2019, 2020 and 2021.
            * **Single-year** data refers to author-specific metrics obtained exclusively in given year. This data is available for the years of 2017, 2019, 2020 and 2021.
            * **Author ranking** goes in descending order, such that a lower ranking indicates a better performance.''',
            link_target="_blank",style = {'font-size':15}), width = {'offset':1, 'size':10})),
        html.Br()], style = {'backgroundColor':darkAccent1}), 
    dbc.Container(fluid = True, children = [
        html.Div(html.Hr(style = {"borderWidth": "1vh", 'borderColor':darkAccent2,"width": "95%", "opacity": "unset",'margin':'auto'})), html.Br(),
        single_author_row,
        html.Div(html.Hr(style = {"borderWidth": "1vh", 'borderColor':darkAccent2,"width": "95%", "opacity": "unset",'margin':'auto'})), html.Br(),
        compare_row,
        # html.Div(html.Hr(style = {"borderWidth": "1vh", 'borderColor':darkAccent2,"width": "95%", "opacity": "unset",'margin':'auto'})), html.Br(),
        # compare_c_metrics_row, html.Br(),
        # html.Div(html.Hr(style = {"borderWidth": "1vh", 'borderColor':darkAccent2,"width": "95%", "opacity": "unset",'margin':'auto'})), html.Br(),
        # compare_misc_metrics_row, html.Br(),
        # html.Div(html.Hr(style = {"borderWidth": "1vh", 'borderColor':darkAccent2,"width": "95%", "opacity": "unset",'margin':'auto'})), html.Br(),
        ], style = {'backgroundColor':darkAccent1})
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
