
# ==========================================================================================
# ==========================================================================================
# IMPORT LIBRARIES
# ==========================================================================================
# ==========================================================================================

# =============== misc libs & modules
import numpy as np
import math
import pickle
import time

# =============== Plotly libs & modules
import plotly.graph_objects as go
import country_converter as coco

# =============== Plotly Dash libraries
from dash import html, dcc, callback, ctx #, Input, Output
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq

# =============== Custom lib
from citations_lib.create_fig_helper_functions import *
from citations_lib.utils import *

def process_results_data(results):
    author_df = pd.DataFrame()
    author_yrs = []
    for cur_data in results.keys():
        if cur_data.split('_')[-1] != "log":
            author_df = pd.concat([author_df, pd.DataFrame.from_records(results[cur_data], index=[0])])
            author_yrs.append(cur_data.split('_')[-1])
    return author_df, author_yrs

def create_author_figures(author_df, author_yrs, metrics_list, author_type, author_name):
    col_list = px.colors.sample_colorscale("turbo", [n/(100-1) for n in range(100)])

    author_df['Year'] = author_yrs
    author_df['self%'] = author_df['self%'] * 100

    subplot_titles = [get_metric_long_name(career=(author_type == 'career'), yr=0, metric=m, include_year=False) for m in metrics_list]
    fig = make_subplots(rows=len(metrics_list), cols=1, subplot_titles=subplot_titles)

    for i, m in enumerate(metrics_list):
        fig.add_trace(go.Scatter(x=author_df['Year'], y=author_df[m],
                                 marker=dict(color=col_list[len(col_list) - i - 25]),
                                 name=m
                                 ), row=i + 1, col=1)
        fig.update_traces(row=i + 1, col=1, hovertemplate='metric in %{x}:<br>%{y}<extra></extra>')

    if author_type == 'singleyr':
        disp_type = 'Single-year'
    else: 
        disp_type = 'Career-long'
    fig.update_xaxes(tickvals=author_yrs, ticktext=author_yrs, gridcolor=darkAccent2, linecolor=darkAccent2, zeroline=False)
    fig.update_yaxes(gridcolor=darkAccent2, linecolor=darkAccent2, zeroline=False)
    fig.update_layout(
        plot_bgcolor=bgc, paper_bgcolor=bgc, font=dict(color=lightAccent1),
        height=2000, showlegend=False,
        title={'text': f"{disp_type} data: {author_name}", 'font': {'size': 20}}, title_x=0.5
    )

    return fig

def single_author_layout():

    # ========================================================================================== 
    # ========================================================================================== 
    # Data prep, color formatting & defining variables
    # ========================================================================================== 
    # ========================================================================================== 
    # This is needed no more! 
    #dfs_career, dfs_singleyr, dfs_career_log, dfs_singleyr_log, _, _, _, _ = load_standardized_data()
    
    darkAccent1 = '#2C2C2C' # dark gray
    darkAccent2 = '#5b5959' # pale gray
    darkAccent3 = '#CFCFCF' # almost white
    lightAccent1 = '#ECAB4C' # ocre
    highlight1 = 'lightsteelblue'
    highlight2 = 'cornflowerblue'

    g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
    g2c = [highlight2, darkAccent3] # bar plot bar 3
    bgc = darkAccent1 # bar plot background
    SUFFIX = '_single_author'

    # =============== Empty fig
    empty_fig = go.Figure()
    empty_fig.update_layout(height = 10, plot_bgcolor = bgc, paper_bgcolor = bgc)
    empty_fig.update_xaxes(visible = False)
    empty_fig.update_yaxes(visible = False)
    # ========================================================================================== 
    # ========================================================================================== 
    # Row 1 Select author and toggle self-citations
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Toggle: % self-citations
    selfC = daq.BooleanSwitch(label = 'Exclude self-citations', labelPosition = 'bottom', id = 'selfCToggle' + SUFFIX)

    # # =============== Author Dropdown
    authorOptions = dcc.Dropdown(options = [], multi = False, id = "authorOptionsDropdown" + SUFFIX, placeholder = 'Start typing (surname name). Hit del to reset.', 
         value = 'Ioannidis, John P.A.', searchable = True)
    
    # # =============== Author Callback
    @callback(
    Output('authorOptionsDropdown' + SUFFIX, 'options'),
    [Input('authorOptionsDropdown' + SUFFIX, 'search_value')]
    )
    def update_output(input1):
        result = get_es_results(input1,['career','singleyr'],'authfull')
        return es_result_pick(result,'authfull')

    @callback(
        Output('careerFig' + SUFFIX, 'figure'),
        Output('singleYrFig' + SUFFIX, 'figure'),
        Output('instLabel' + SUFFIX, 'children'),
        Output('fieldLabel' + SUFFIX, 'children'),
        Output('authorOptionsDropdown' + SUFFIX, 'placeholder'),
        Input('authorOptionsDropdown' + SUFFIX, 'value'),
        Input('selfCToggle' + SUFFIX, 'on'))
    def update_Author1(author, ns):
        exists_career_data = True
        exists_single_data = True

        if author == None: raise PreventUpdate
        else:
            results_career = get_es_results(author,'career','authfull')
            #print(results_career)
            results_career = es_result_pick(results_career,'data', None)

            results_singleyr = get_es_results(author,'singleyr','authfull')
            results_singleyr  = es_result_pick(results_singleyr,'data', None)
            
            inst_name = ''
            field_name = ''
            if results_career is not None:
                inst_name = results_career[list(results_career.keys())[-1]]["inst_name"]
                field_name = results_career[list(results_career.keys())[-1]]["sm-field"]
            else:
                exists_career_data = False
            
            if results_singleyr is None:
                exists_single_data = False

            metrics_list = ['rank', 'c', 'nc','h', 'hm', 'ncs','ncsf','ncsfl','nps','cpsf','npsfl','npciting']
            metrics_list = [i + ' (ns)' if ns else i for i in metrics_list]
            metrics_list += ['np' ,'self%']

            if exists_career_data:
                career_author_df, career_yrs = process_results_data(results_career)
                fig_career = create_author_figures(career_author_df, career_yrs, metrics_list, "career", author)
            else:
                fig_career = empty_fig

            if exists_single_data:
                singleyr_author_df, singleyr_yrs = process_results_data(results_singleyr)
                fig_singleyr = create_author_figures(singleyr_author_df, singleyr_yrs, metrics_list, "singleyr", author)
            else: 
                fig_singleyr = empty_fig

            
            

            return(fig_career, fig_singleyr, inst_name, field_name, "Start typing for new search | Displaying: " + author.split(",")[0])

    # =============== Row 1: Author select
    row1 = dbc.Row([dbc.Col(html.Center(authorOptions), width = {'offset':3,'size':4}),
        dbc.Col(html.Center(selfC),width = {'size':2})])

    # =============== Row 2: Figures
    row2 = dbc.Row([
        dbc.Col([html.Code(html.Label(id='instLabel' + SUFFIX,children=""))], width = {'offset':0, 'size':1}),
        dbc.Col([html.Center(dcc.Graph(id = 'careerFig' + SUFFIX, figure = empty_fig, config = {'displayModeBar': False}))], width = {'offset':0, 'size':5}),
        dbc.Col([html.Center(dcc.Graph(id = 'singleYrFig' + SUFFIX, figure = empty_fig, config = {'displayModeBar': False}))], width = {'size':5}),
        dbc.Col([html.Code(html.Label(id='fieldLabel' + SUFFIX,children=""))], width = {'offset':0, 'size':1})
    ])



    return(html.Div([
        dbc.Container(fluid = True, children = [
            html.Br(),
            html.Label(id='tmpLabel',children=""),
            row1, html.Hr(), 
            row2, html.Br(), 
        ], style = {'backgroundColor':darkAccent1}), 
    ]))