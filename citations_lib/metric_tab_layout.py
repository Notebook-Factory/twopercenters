#!/usr/bin/env python
# coding: utf-8

# ============================================= 
# IMPORT LIBRARIES
# ============================================= 

# =============== main libs & modules
import numpy as np
import pandas as pd
import dash_bootstrap_components as dbc
import pickle
import dash_daq as daq
from dash.exceptions import PreventUpdate

import plotly.graph_objects as go
from IPython.core.display import display, HTML
from plotly.offline import plot
import plotly.express as px
import plotly.colors
from plotly.subplots import make_subplots

# =============== Plotly Dash libraries
import dash
from dash import html, dcc, callback
import dash_daq as daq
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc

# =============== Custom lib
from citations_lib.create_fig_helper_functions import *
from citations_lib.utils import *

# ============================================= 
# Data Preparation
# ============================================= 



def get_metric_tab_layout(): # DEFAULT_CAREER = None, DEFAULT_YR = None
    CURR_METRIC = "something"
    CURR_TITLE = "something else"
    DEFAULT_CAREER = True 
    DEFAULT_YR = 3
    #aa = pd.read_pickle('cntry_sum.pkl')
    # world_path = 'aggregate/custom.geo.json'
    # with open(world_path) as f: geo_world = json.load(f)
    
    darkAccent1 = '#2C2C2C' # dark gray
    darkAccent2 = '#5b5959' # pale gray
    darkAccent3 = '#CFCFCF' # almost white
    lightAccent1 = '#ECAB4C' # ocre
    highlight1 = 'lightsteelblue'
    highlight2 = 'cornflowerblue'
    theme =  {'dark': True,'detail': lightAccent1,'primary': darkAccent1,'secondary': lightAccent1}
    g1c = [highlight1,highlight1, darkAccent2, darkAccent2] # bar plot bars 1 & 2
    g2c = [highlight2, highlight2] # bar plot bar 3
    bgc = darkAccent1 # bar plot background

    #dfs_career, dfs_singleyr, dfs_career_log, dfs_singleyr_log, _, _, _, _ = load_standardized_data()
    dropdown_opts = dict()
    # for i in range(5):
    #     with open(f'aggregate/info_career_{i}.pkl', 'rb') as fp:
    #         info = pickle.load(fp)
    #     dropdown_opts['career '+ str(i)] = info
    # for i in range(4):
    #     with open(f'aggregate/info_singleyr_{i}.pkl', 'rb') as fp:
    #         info = pickle.load(fp)
    #     dropdown_opts['singleyr '+ str(i)] = info

    # ============================================= 
    # Option selection buttons
    # ============================================= 

    # =============== Card: 'Select dataset'
    selectStep1 = dbc.Card(dbc.CardBody(html.Center("Select dataset", style = {'color':darkAccent3, 'font-size':20})),color = darkAccent2)

    # =============== Career vs Singleyr
    careerORSingleYr = html.Div([
        dbc.RadioItems(id = CURR_METRIC + "careerORSingleYrRadio", value = DEFAULT_CAREER, className = "btn-group", inputClassName = "btn-check", labelClassName = "btn btn-outline-primary",
            labelCheckedClassName = "active", options = [{"label": "Career", "value": True}, {"label": "Single year", "value": False}, 
        ])], className = "radio-group")
    
    # =============== Year
    # def update_yr_options(career):
    #     if career == False: return [{"label": "2017", "value": 0, 'disabled': False}, {"label": "2018", 'disabled': True}, {"label": "2019", "value": 1, 'disabled': False}, 
    #         {"label": "2020", "value": 2, 'disabled': False}, {"label": "2021", "value": 3, 'disabled': False}]
    #     else: return [{"label": "2017", "value": 0, 'disabled': False}, {"label": "2018", "value": 1, 'disabled': False}, 
    #         {"label": "2019", "value": 2, 'disabled': False}, {"label": "2020", "value": 3, 'disabled': False}, {"label": "2021", "value": 4, 'disabled': False}]
    selectYr = html.Div(
        [dbc.RadioItems(
            id = CURR_METRIC + "selectYrRadio", value = DEFAULT_YR, className = "btn-group", inputClassName = "btn-check", 
            labelClassName = "btn btn-outline-primary", labelCheckedClassName = "active", style = {'size':'sm'}, 
            options = update_yr_options(career = True))
    ], className = "radio-group")
    @callback(
        Output(CURR_METRIC + 'selectYrRadio', 'options'), 
        Input(CURR_METRIC + 'careerORSingleYrRadio', 'value'))
    def update_yr_opts(career):
        return(update_yr_options(career))
    
    # =============== Toggle: % self-citations
    selfC = daq.BooleanSwitch(
        label = 'Self-citations excluded',
        labelPosition = 'bottom',
        id = CURR_METRIC + 'selfCToggle', on = False)
    
    # =============== Row 0
    row0 = dbc.Row([dbc.Col(html.Center(selectStep1), width = {'offset':1, 'size':2}),
        dbc.Col(html.Center(careerORSingleYr), width = {'offset':1, 'size':2}),
        dbc.Col(html.Center(selectYr), width = {'offset':1, 'size':4})])
    
    # ============================================= 
    # Figures
    # ============================================= 
        
    # =============== Empty fig
    empty_fig = go.Figure()
    empty_fig.update_layout(plot_bgcolor = bgc, paper_bgcolor = bgc, height = 50,
        xaxis = {'tickmode':'array', 'tickvals':[]},
        yaxis = {'tickmode':'array', 'tickvals':[]},
        template = None)
    empty_fig.update_xaxes(visible = False)
    empty_fig.update_yaxes(visible = False)

    # =============== Toggle: log-transform values for each figure
    #logTransf1 = daq.BooleanSwitch(label = 'Log transformed',labelPosition = 'bottom', id = CURR_METRIC + 'logTransfToggle1',on = True)
    logTransf2 = daq.BooleanSwitch(label = 'Log transformed',labelPosition = 'bottom', id = CURR_METRIC + 'logTransfToggle2',on = True)
    #logTransf3 = daq.BooleanSwitch(label = 'Log transformed',labelPosition = 'bottom', id = CURR_METRIC + 'logTransfToggle3',on = True)

    # =============== Toggle: include or exclude % self-citations for each figure
    #selfC1 = daq.BooleanSwitch(label = 'Exclude self-citations', labelPosition = 'bottom', id = CURR_METRIC + 'selfCToggle1')
    selfC2 = daq.BooleanSwitch(label = 'Exclude self-citations', labelPosition = 'bottom', id = CURR_METRIC + 'selfCToggle2')
    #selfC3 = daq.BooleanSwitch(label = 'Exclude self-citations', labelPosition = 'bottom', id = CURR_METRIC + 'selfCToggle3')

    # =============== Figure titles
   # figTitle1 = html.Div(' ', id = CURR_METRIC + 'figTitleCard1', style = {'color':lightAccent1, 'font-size':25})
    figTitle2 = html.Div(' ', id = CURR_METRIC + 'figTitleCard2', style = {'color':lightAccent1, 'font-size':25})
    #figTitle3 = html.Div(' ', id = CURR_METRIC + 'figTitleCard3', style = {'color':lightAccent1, 'font-size':25})

    # =============== Figure 1: violin plots by field
    # fig1 = dcc.Graph(id = CURR_METRIC + 'fig1', figure =  empty_fig,config = {'displayModeBar': False})
    # @callback(
    #     Output(CURR_METRIC + 'fig1', 'figure'),
    #     Output(CURR_METRIC + 'figTitleCard1', 'children'),
    #     Input(CURR_METRIC + 'careerORSingleYrRadio','value'),
    #     Input(CURR_METRIC + 'selectYrRadio','value'),
    #     Input(CURR_METRIC + 'selfCToggle1','on'),
    #     Input(CURR_METRIC + 'logTransfToggle1','on'))
    # def update_figs_metric(career, yr, ns, logTransf, CURR_METRIC = CURR_METRIC):
    #     if career == None or yr == None: return(empty_fig, 'No dataset selected')
    #     else:
    #         if ns == True: CURR_METRIC = CURR_METRIC + ' (ns)' 
    #         if career == True:
    #             df = dfs_career[yr].copy()
    #             df_log = dfs_career_log[yr].copy()
    #         else:
    #             df = dfs_singleyr[yr].copy()
    #             df_log = dfs_singleyr_log[yr].copy()
    #         col_list = px.colors.sample_colorscale("turbo", [n/(200-1) for n in range(200)])
            
    #         # Hover: show author names for outlier according to plotly go.Violin(points): < 4*Q1-3*Q3 or > 4*Q3-3*Q1 
    #         q1 = df[CURR_METRIC].quantile(0.25)
    #         q3 = df[CURR_METRIC].quantile(0.75)
    #         outlier_min = (4*q1) - (3*q3)
    #         outlier_max = (4*q3) - (3*q1)
    #         df['hover'] = df['authfull'] + '<br>mean: '+str(round(df[CURR_METRIC].mean(),0))+'<br>'+'std: '+str(round(df[CURR_METRIC].std(),0)) + '<extra></extra>'
    #         df.loc[(df[CURR_METRIC]  <= outlier_max) & (df[CURR_METRIC]  >= outlier_min), ['hover']] = 'mean: '+str(round(df[CURR_METRIC].mean(),0))+'<br>'+'std: '+str(round(df[CURR_METRIC].std(),0)) + '<extra></extra>'

    #         fig = go.Figure()
    #         # histogram across all fields
    #         if logTransf and CURR_METRIC != 'c' and CURR_METRIC != 'c (ns)': fig.add_trace(go.Violin(name = 'All', y = df_log[CURR_METRIC], text = df['hover'], hovertemplate = "%{text}<br>%{x}<br>y: %{y}", meanline_visible = True, marker_color = highlight2))
    #         else: fig.add_trace(go.Violin(name = 'All', y = df[CURR_METRIC], text = df['hover'], hovertemplate = "%{text}<br>%{x}<br>y: %{y}", meanline_visible = True, marker_color = highlight2))
            
    #         # field-specific histograms:
    #         for j, field in enumerate(df['sm-field'].unique()):
    #             q1 = df[df['sm-field'] == field][CURR_METRIC].quantile(0.25) # alternative: df_tmp = df[df['sm-field'] == field]
    #             q3 = df[df['sm-field'] == field][CURR_METRIC].quantile(0.75)
    #             outlier_min = (4*q1) - (3*q3)
    #             outlier_max = (4*q3) - (3*q1)
    #             df['hover' + field] = df['authfull'] + '<br>mean: '+str(round(df[df['sm-field'] == field][CURR_METRIC].mean(),0))+'<br>'+'std: '+str(round(df[df['sm-field'] == field][CURR_METRIC].std(),0)) + '<extra></extra>'
    #             df.loc[(df[CURR_METRIC]  <= outlier_max) & (df[CURR_METRIC]  >= outlier_min) & (df['sm-field'] == field), ['hover' + field]] = '<br>mean: '+str(round(df[df['sm-field'] == field][CURR_METRIC].mean(),0))+'<br>'+'std: '+str(round(df[df['sm-field'] == field][CURR_METRIC].std(),0)) + '<extra></extra>'
    #             if logTransf and CURR_METRIC != 'c' and CURR_METRIC != 'c (ns)': fig.add_trace(go.Violin(name = field,
    #                 x = df_log[df_log['sm-field'] == field]['sm-field'], y = df_log[df_log['sm-field'] == field][CURR_METRIC],
    #                 text = df[df['sm-field'] == field]['hover' + field], hovertemplate = "%{text}<br>%{x}<br>y: %{y}", meanline_visible = True, marker_color = col_list[len(col_list)-j-50]))
    #             else: fig.add_trace(go.Violin(name = field,
    #                 x = df[df['sm-field'] == field]['sm-field'], y = df[df['sm-field'] == field][CURR_METRIC],
    #                 text = df[df['sm-field'] == field]['hover' + field], hovertemplate = "%{text}<br>%{x}<br>y: %{y}", meanline_visible = True, marker_color = col_list[len(col_list)-j-50]))

    #         # Update fig params
    #         if logTransf and CURR_METRIC != 'c' and CURR_METRIC != 'c (ns)':
    #             if CURR_METRIC != 'c' and CURR_METRIC != 'c (ns)': fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2,
    #                 tickvals = [k*(df_log[CURR_METRIC].max()/8) for k in range(0,8)],
    #                 ticktext = [int(np.exp(k*(df_log[CURR_METRIC].max()/8)*(np.log(df[CURR_METRIC].max() + 1)))) for k in range(0,8)],
    #                 range = [0, df_log[CURR_METRIC].max()])
    #             else: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2,linecolor = darkAccent2)
    #         fig.update_layout(plot_bgcolor = bgc,paper_bgcolor = bgc,font = dict(color = lightAccent1),showlegend = False,height = 700, margin = {'t':0})
    #         fig.update_xaxes(linecolor = darkAccent2, tickfont=dict(size=15), tickangle=45)
            
    #         # fig title
    #         if logTransf and CURR_METRIC != 'c' and CURR_METRIC != 'c (ns)': title = 'Log-transformed ' + get_metric_long_name(career, yr, CURR_METRIC) + ' – Violin Plots By Field'
    #         else: title = get_metric_long_name(career, yr, CURR_METRIC) + ' – Violin Plots By Field'
    #         title = title.title()
    #         return(fig, title)
    # =============== Row: Figure 1
    # row1 = html.Div([
    #     dbc.Row(dbc.Col(html.Center(figTitle1))), dbc.Row(html.Br()), 
    #     dbc.Row([dbc.Col(logTransf1, width = {'offset':4, 'size':2}), dbc.Col(selfC1, width = {'size':2})]), 
    #     dbc.Row(fig1), dbc.Row(html.Br())])
    
    # =============== Figure 2: geo plot
    fig2_dd = dcc.Dropdown(
        multi = False, value = 'count', id = CURR_METRIC + "fig2_dd", placeholder = 'Select statistic to plot',
        #style = {'color':darkAccent3,'background-color':darkAccent2}, className = 'newDD',
        options = [{'label':'Count','value':'count'}, {'label':'Median','value':'median'},
             {'label':'Minimum','value':'min'},
            {'label':'Maximum','value':'max'}, {'label':'25th percentile','value':'25%'},
             {'label':'75th percentile','value':'75%'}])
    #fig2 = dcc.Graph(id = CURR_METRIC + 'fig2', figure = create_geo_json(df_in = dfs_career[0], df_in_log = dfs_career[0], career = True, yr = 0, metric = CURR_METRIC, empty = True)[0]) # default settings!
    fig2 = dcc.Graph(id = CURR_METRIC + 'fig2', figure = empty_fig)
    #fig2 = empty_fig
    @callback(
        Output(CURR_METRIC + 'fig2_dd', 'figure'),
        Output(CURR_METRIC + 'figTitleCard2', 'children'),
        Input(CURR_METRIC + 'careerORSingleYrRadio','value'),
        #Input(CURR_METRIC + 'selectYrRadio','value'),
        #Input(CURR_METRIC + 'selfCToggle2','on'),
        #Input(CURR_METRIC + 'logTransfToggle2','on'),
        #Input(CURR_METRIC + 'fig2_dd','value')
        Input("fig-store", "data"),
        #Input("geo-store", "data"),
        )
    def update_figs_metric(bb,fig):
        if fig is None:
            raise PreventUpdate
        #fig = get_es_geo(aa,'2021',CURR_METRIC,3,'',geo_world )
        title = 'snfnskfs'
        print(type(fig))
        #fig, title = create_geo_json(df_in = dfs[yr], df_in_log = dfs_log[yr], career = career, yr = yr, metric = CURR_METRIC, color_by = geoColor, logTransf = logTransf)
        #fig.update_layout(height = 600, coloraxis_colorbar_x = 0.8)
        return(fig, title)
    # =============== Row: Figure 2
    row2 = html.Div([
        dbc.Row(dbc.Col(html.Center(figTitle2))), dbc.Row(html.Br()), 
        dbc.Row([dbc.Col(html.Center(logTransf2), width = {'offset':4, 'size':2}), dbc.Col(html.Center(selfC2), width = {'size':2})]),
        dbc.Row(dbc.Col(html.Center(fig2_dd), width = {'offset':4,'size':4})),
        dbc.Row(fig2),dbc.Row(html.Br())])

    # # =============== Figure 3: violin plots by time
    # fig3 = dcc.Graph(id = CURR_METRIC + 'fig3', figure =  empty_fig, config = {'displayModeBar': False})
    # @callback(
    #     Output(CURR_METRIC + 'fig3', 'figure'),
    #     Output(CURR_METRIC + 'figTitleCard3', 'children'),
    #     Input(CURR_METRIC + 'careerORSingleYrRadio','value'),
    #     Input(CURR_METRIC + 'selfCToggle3','on'),
    #     Input(CURR_METRIC + 'logTransfToggle3','on'))
    # def update_figs_metric(career, ns, logTransf, CURR_METRIC = CURR_METRIC):
    #     if career == None: return(empty_fig, 'No dataset selected')
    #     else:
    #         if ns == True: CURR_METRIC = CURR_METRIC + ' (ns)' 
    #         if career == True:
    #             dfs = dfs_career.copy()
    #             dfs_log = dfs_career_log.copy()
    #         else:
    #             dfs = dfs_singleyr.copy()
    #             dfs_log = dfs_singleyr_log.copy()
    #         # Fig params
    #         col_list = px.colors.sample_colorscale("turbo", [n/(200-1) for n in range(200)])
    #         vert_space = 0.05
    #         yrs = [2017,2018,2019,2020,2021] if career else [2017,2019,2020,2021]
    #         max_x_vals = []
    #         max_x_vals_log = []
    #         for i in range(len(dfs)): 
    #             max_x_vals.append(dfs[i][CURR_METRIC].max())
    #             max_x_vals_log.append(dfs_log[i][CURR_METRIC].max())
    #         max_x = max(max_x_vals)
    #         max_x_log = max(max_x_vals_log)
    #         title_list = []
    #         for i in range(len(dfs)): title_list.append(str(yrs[i]) + '<br>Mean: ' + str(int(round(dfs[i][CURR_METRIC].mean(),0))))
    #         # Make subplots
    #         fig = make_subplots(rows = len(yrs), cols = 1, shared_yaxes=True,vertical_spacing=vert_space, subplot_titles = title_list)
    #         for i in range(len(dfs)):
    #             hovertemp = 'mean: '+str(round(dfs[i][CURR_METRIC].mean(),0))+'<br>'+'std: '+str(round(dfs[i][CURR_METRIC].std(),0))+'<br>'+ CURR_METRIC+ ': %{x}<br>count: %{y}<extra></extra>'
    #             if logTransf and CURR_METRIC != 'c' and CURR_METRIC != 'c (ns)': 
    #                 fig.add_trace(go.Histogram(name = yrs[i], x = dfs_log[i][CURR_METRIC], marker_color = col_list[len(col_list)-(i*5)-50]), row = i + 1, col = 1)
    #                 fig.update_xaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2,zeroline = False,
    #                     tickvals = [k*(max_x_log/10) for k in range(0,10)], ticktext = [int(np.exp(k*(max_x_log/10)*(np.log(max_x + 1)))) for k in range(0,10)], range = [0, max_x_log])
    #                 title = 'Log-transformed ' + get_metric_long_name(career, 0, CURR_METRIC, include_year = False).title() + ' Over Time'
    #             else:
    #                 fig.add_trace(go.Histogram(name = yrs[i],x = dfs[i][CURR_METRIC], marker_color = col_list[len(col_list)-(i*5)-50]), row = i + 1, col = 1)
    #                 fig.update_xaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2,zeroline = False, range = [0, max_x])
    #                 title = get_metric_long_name(career, 0, CURR_METRIC, include_year = False).title() + ' Over Time'
    #             fig.update_traces(row = i + 1, col = 1, hovertemplate = hovertemp)
            
    #         # Layout
    #         fig.update_layout(plot_bgcolor = bgc,paper_bgcolor = bgc,font = dict(color = lightAccent1),height = 800, showlegend = False, margin = {'t':0, 'l':200,'r':200})
    #         for i in range(len(dfs)): fig.layout.annotations[i].update(x=-0.06, y = fig.layout.annotations[i]['y']-0.07)
    #         fig.update_yaxes(showgrid = False, zeroline = False, showticklabels = False)
    #         fig.update_xaxes(showgrid = True, zeroline = False, gridcolor = darkAccent2,linecolor = darkAccent2)
    #         return(fig,title)
    # row3 = html.Div([
    #     dbc.Row(dbc.Col(html.Center(figTitle3))), dbc.Row(html.Br()), 
    #     dbc.Row([dbc.Col(logTransf3, width = {'offset':4, 'size':2}), dbc.Col(selfC3, width = {'size':2})]), 
    #     dbc.Row(html.Br()), fig3, dbc.Row(html.Br())])

    # ============================================= 
    # Layout
    # ============================================= 

    return(html.Div([
        html.Div(children = [html.H1(children = CURR_TITLE, className = "header-title2")],className = "header2"),
        dbc.Container(fluid = True, children = [
            dbc.Row(html.Hr()),dbc.Row(html.Br()), row0,
            #dbc.Row(html.Br()),dbc.Row(html.Hr()), row1,
            dbc.Row(html.Br()),dbc.Row(html.Hr()), row2,
            #dbc.Row(html.Br()),dbc.Row(html.Hr()), row3,
            dbc.Row(html.Br())
        ], style = {'backgroundColor':darkAccent1}),
        # dbc.Tooltip("Options selected in this row determine what dataset metrics are obtained from.", target = "selectStep1Card",placement = "right"), dbc.Tooltip("Exclude or include author self citations.", target = "selfCToggle",placement = "right"), dbc.Tooltip("Author metrics from entire career-span ('Career') or just from year of interest ('Single year').", target = "careerORSingleYrRadio",placement = "right"), dbc.Tooltip("Note: single year data not available for 2018.", target = "selectYrRadioRadio",placement = "right")
    ]))
