
# # ==========================================================================================
# # ==========================================================================================
# # IMPORT LIBRARIES
# # ==========================================================================================
# # ==========================================================================================

# # =============== misc libs & modules
# import numpy as np
# import math
# import pickle

# # =============== Plotly libs & modules
# import plotly.graph_objects as go
# import country_converter as coco

# # =============== Plotly Dash libraries
# import dash
# from dash import html, dcc, callback, ctx #, Input, Output
# from dash.dependencies import Input, Output, State
# from dash.exceptions import PreventUpdate
# import dash_bootstrap_components as dbc
# import dash_daq as daq

# # =============== Custom lib
# from citations_lib.create_fig_helper_functions import *
# from citations_lib.utils import *

# # =============== Register page
# dash.register_page(__name__)

# # ========================================================================================== 
# # ========================================================================================== 
# # Data Preparation
# # ========================================================================================== 
# # ========================================================================================== 

# dfs_career, dfs_singleyr, dfs_career_log, dfs_singleyr_log, _, _, _, _ = load_standardized_data()

# # ========================================================================================== 
# # ========================================================================================== 
# # Color formatting & defining variables
# # ========================================================================================== 
# # ========================================================================================== 
# darkAccent1 = '#2C2C2C' # dark gray
# darkAccent2 = '#5b5959' # pale gray
# darkAccent3 = '#CFCFCF' # almost white
# lightAccent1 = '#ECAB4C' # ocre
# highlight1 = 'lightsteelblue'
# highlight2 = 'cornflowerblue'

# g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
# g2c = [highlight2, darkAccent3] # bar plot bar 3
# bgc = darkAccent1 # bar plot background
# SUFFIX = '_test'

# # =============== Empty fig
# empty_fig = go.Figure()
# empty_fig.update_layout(height = 10, plot_bgcolor = bgc, paper_bgcolor = bgc)
# empty_fig.update_xaxes(visible = False)
# empty_fig.update_yaxes(visible = False)
# # ========================================================================================== 
# # ========================================================================================== 
# # Row 1 Select author and toggle self-citations
# # ========================================================================================== 
# # ========================================================================================== 

# # =============== Toggle: % self-citations
# selfC = daq.BooleanSwitch(label = 'Exclude self-citations', labelPosition = 'bottom', id = 'selfCToggle' + SUFFIX)

# # =============== Full list of authors across dataset versions
# full_author_list = []
# for i in range(len(dfs_career)): full_author_list += list(dfs_career[i]['authfull'].unique())
# full_author_list = list(set(full_author_list))
# full_author_list = [str(i).title() for i in full_author_list]
# full_author_list.remove('Nan')
# full_author_list.sort()
# # =============== Author Dropdown
# authorOptions = dcc.Dropdown(options = [], placeholder = 'Select author', multi = False, id = "authorOptionsDropdown" + SUFFIX, 
#     value = None, searchable = True, style = {'background-color':darkAccent3})
# # =============== Author Callback
# @callback(
#     Output('authorOptionsDropdown' + SUFFIX, 'options'), 
#     Input('authorOptionsDropdown' + SUFFIX, 'search_value'))
# def update_AuthorDropdown(search_value):
#     if not search_value: raise PreventUpdate
#     else:
#         optns = [{'label':name, 'value':name} for name in full_author_list] # dynamic dropdown to speed things up
#         return [o for o in optns if search_value in o["label"]]
 
# @callback(
#     Output('careerFig' + SUFFIX, 'figure'),
#     Output('singleYrFig' + SUFFIX, 'figure'),
#     Input('authorOptionsDropdown' + SUFFIX, 'value'),
#     Input('selfCToggle' + SUFFIX, 'on'))
# def update_Author1(author, ns):
#     if author == None: raise PreventUpdate
#     else:
#         # =============== defining vars
#         metrics_list = ['rank', 'c', 'nc','h', 'hm', 'ncs','ncsf','ncsfl','nps','cpsf','npsfl','npciting']      
#         metrics_list = [i + ' (ns)' if ns else i for i in metrics_list]
#         metrics_list += ['np' ,'self%']
#         col_list = px.colors.sample_colorscale("turbo", [n/(100-1) for n in range(100)])

#         # =============== career fig
#         career_yrs_full = [2017, 2018, 2019, 2020, 2021]
#         career_author_df = pd.DataFrame()
#         career_author_df_log = pd.DataFrame()
#         career_yrs = []
#         for i in range(len(dfs_career)):
#             tmp = dfs_career[i][dfs_career[i]['authfull'] == author]
#             if tmp.shape[0] == 1: # we won't be looking at duplicate authors for now!
#                 career_author_df = pd.concat([career_author_df, tmp[tmp['authfull'] == author]])
#                 career_author_df_log = pd.concat([career_author_df_log, dfs_career_log[i][dfs_career_log[i]['authfull'] == author]])
#                 career_yrs.append(career_yrs_full[i])
#         career_author_df['Year'] = career_yrs
#         career_author_df['self%'] = career_author_df['self%']*100
#         career_author_df_log['self%'] = career_author_df_log['self%']*5 # makes it visible during log transform
#         subplot_titles_career = [get_metric_long_name(career = True, yr = 0, metric = m, include_year = False) for m in metrics_list]
#         fig_career = make_subplots(rows = len(metrics_list), cols = 1, subplot_titles = subplot_titles_career)
#         for i,m in enumerate(metrics_list):
#             fig_career.add_trace(go.Scatter(x = career_author_df['Year'], y = career_author_df[m],
#                 mode='markers',
#                 marker=dict(size=career_author_df_log[m]*30, color = col_list[len(col_list)-i-25]),
#                 name=m
#                 ), row = i+1, col = 1)
#             fig_career.update_traces(row = i+1, col = 1, hovertemplate = 'metric in %{x}:<br>%{y}<extra></extra>')
#         fig_career.update_xaxes(tickvals = career_yrs, ticktext = career_yrs, gridcolor = darkAccent2, linecolor = darkAccent2, zeroline = False)
#         fig_career.update_yaxes(gridcolor = darkAccent2, linecolor = darkAccent2, zeroline = False)
#         fig_career.update_layout(
#             plot_bgcolor = bgc,paper_bgcolor = bgc,font = dict(color = lightAccent1),
#             height = 2000, showlegend = False,
#             title = {'text':'Career-long data','font':{'size':20}},title_x = 0.5)
        
#         # =============== single year fig
#         singleyr_yrs_full = [2017, 2019, 2020, 2021]
#         singleyr_author_df = pd.DataFrame()
#         singleyr_author_df_log = pd.DataFrame()
#         singleyr_yrs = []
#         for i in range(len(dfs_singleyr)):
#             tmp = dfs_singleyr[i][dfs_singleyr[i]['authfull'] == author]
#             if tmp.shape[0] == 1: # we won't be looking at duplicate authors for now!
#                 singleyr_author_df = pd.concat([singleyr_author_df, tmp[tmp['authfull'] == author]])
#                 singleyr_author_df_log = pd.concat([singleyr_author_df_log, dfs_singleyr_log[i][dfs_singleyr_log[i]['authfull'] == author]])
#                 singleyr_yrs.append(singleyr_yrs_full[i])
#         singleyr_author_df['Year'] = singleyr_yrs
#         singleyr_author_df['self%'] = singleyr_author_df['self%']*100
#         singleyr_author_df_log['self%'] = singleyr_author_df_log['self%']*5 # makes it visible during log transform
#         subplot_titles_singleyr = [get_metric_long_name(career = False, yr = 0, metric = m, include_year = False) for m in metrics_list]
#         fig_singleyr = make_subplots(rows = len(metrics_list), cols = 1, subplot_titles = subplot_titles_singleyr)
#         for i,m in enumerate(metrics_list):
#             fig_singleyr.add_trace(go.Scatter(x = singleyr_author_df['Year'], y = singleyr_author_df[m],
#                 mode='markers',
#                 marker=dict(size=singleyr_author_df_log[m]*30, color = col_list[len(col_list)-i-25]),
#                 name=m
#                 ), row = i+1, col = 1)
#             fig_singleyr.update_traces(row = i+1, col = 1, hovertemplate = 'metric in %{x}:<br>%{y}<extra></extra>')
#         fig_singleyr.update_xaxes(tickvals = singleyr_yrs, ticktext = singleyr_yrs, gridcolor = darkAccent2, linecolor = darkAccent2, zeroline = False)
#         fig_singleyr.update_yaxes(gridcolor = darkAccent2, linecolor = darkAccent2, zeroline = False)
#         fig_singleyr.update_layout(
#             plot_bgcolor = bgc,paper_bgcolor = bgc,font = dict(color = lightAccent1),
#             height = 2000, showlegend = False,
#             title = {'text':'Single-year data','font':{'size':20}},title_x = 0.5)
        
#         return(fig_career, fig_singleyr)

# # =============== Row 1: Author select
# row1 = dbc.Row([dbc.Col(html.Center(authorOptions), width = {'offset':3,'size':4}),
#     dbc.Col(html.Center(selfC),width = {'size':2})])

# # =============== Row 2: Figures
# row2 = dbc.Row([
#     dbc.Col([html.Center(dcc.Graph(id = 'careerFig' + SUFFIX, figure = empty_fig, config = {'displayModeBar': False}))], width = {'offset':1, 'size':5}),
#     dbc.Col([html.Center(dcc.Graph(id = 'singleYrFig' + SUFFIX, figure = empty_fig, config = {'displayModeBar': False}))], width = {'size':5})
# ])

# # ========================================================================================== 
# # ========================================================================================== 
# # Layout
# # ========================================================================================== 
# # ========================================================================================== 
# layout = html.Div([
#     dbc.Container(fluid = True, children = [
#         dbc.Row(html.Br()), 
#         row1, html.Hr(), 
#         row2, html.Hr(), html.Br(), 
#     ], style = {'backgroundColor':darkAccent1}), 
# ])