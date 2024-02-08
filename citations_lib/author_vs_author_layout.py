
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


def author_vs_author_layout():

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
    darkAccent1 = '#2C2C2C' # dark gray
    darkAccent2 = '#5b5959' # pale gray
    darkAccent3 = '#CFCFCF' # almost white
    lightAccent1 = '#ECAB4C' # ocre
    highlight1 = 'lightsteelblue'
    highlight2 = 'cornflowerblue'

    g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
    g2c = [highlight2, darkAccent3] # bar plot bar 3
    bgc = darkAccent1 # bar plot background
    SUFFIX = '_author_vs_author'

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 1: select dataset!
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Select dataset!
    selectStep1 = dbc.Card(dbc.CardBody(html.Center("Select dataset", style = {'color':darkAccent3, 'font-size':20})),color = darkAccent2)

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
    
    careerORSingleA2 = html.Div([
        dbc.RadioItems(
            id = "careerORSingleYrA2" + SUFFIX, 
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
    ], className = "radio-group")
    
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
    ], className = "radio-group")

    selectYrA2 = html.Div(
        [dbc.RadioItems(
            id = "selectYrRadioA2" + SUFFIX, 
            className = "btn-group", 
            inputClassName = "btn-check", 
            labelClassName = "btn btn-outline-primary", 
            labelCheckedClassName = "active", 
            style = {'size':'sm'}, 
            value = '2017',
            options = [{"label": "2017", "value": "2017", 'disabled': False}]
        )
    ], className = "radio-group")

    @callback(
        Output('selectYrRadio' + SUFFIX, 'options'), 
        Input('careerORSingleYrRadio' + SUFFIX, 'value'))
    def update_yr_opts(career):
        return(update_yr_options(career))

    row1 = dbc.Row([dbc.Col(html.Center(selectStep1), width = {'offset':1,'size':3}), 
            dbc.Col(html.Center(careerORSingleYr), width = 2), 
            dbc.Col(html.Center(selectYr), width = 5)])

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 2 Select authors!
    # ========================================================================================== 
    # ========================================================================================== 

    author1Options = dcc.Dropdown(options = [], placeholder = 'Author 1: Start typing name and surname', multi = False, id = "author1OptionsDropdown" + SUFFIX, 
        value = 'Ioannidis, John P.A.', searchable = True)
    generate_es_dropdown_callback("author1OptionsDropdown" + SUFFIX)
    generate_update_carsing_callback('author1OptionsDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX)
    generate_update_years_callback('careerORSingleYrA1' + SUFFIX, 'selectYrRadioA1' + SUFFIX, 'author1OptionsDropdown' + SUFFIX)
    output_ids = ['InfoAuthor1' + SUFFIX, 'FieldAuthor1' + SUFFIX, 'CountryAuthor1' + SUFFIX, 'InstitutionAuthor1' + SUFFIX]
    generate_update_cards_callback('selectYrRadioA1' + SUFFIX, output_ids, 'author1OptionsDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX,darkAccent1, highlight1)

    # =============== Author 2 Callbacks
    author2Options = dcc.Dropdown(options = [], placeholder = 'Author 2: Start typing name and surname', multi = False, id = "author2OptionsDropdown" + SUFFIX, 
    value = 'Bengio, Yoshua', searchable = True)
    generate_es_dropdown_callback("author2OptionsDropdown" + SUFFIX)
    generate_update_carsing_callback('author2OptionsDropdown' + SUFFIX, 'careerORSingleYrA2' + SUFFIX)
    generate_update_years_callback('careerORSingleYrA2' + SUFFIX, 'selectYrRadioA2' + SUFFIX, 'author2OptionsDropdown' + SUFFIX)
    output_ids = ['InfoAuthor2' + SUFFIX, 'FieldAuthor2' + SUFFIX, 'CountryAuthor2' + SUFFIX, 'InstitutionAuthor2' + SUFFIX]
    generate_update_cards_callback('selectYrRadioA2' + SUFFIX, output_ids, 'author2OptionsDropdown' + SUFFIX, 'careerORSingleYrA2' + SUFFIX, darkAccent1, highlight2)
   
    row2 = dbc.Container([
        dbc.Row([
            dbc.Col([author1Options, dbc.Row([ dbc.Col([careerORSingleA1],width=4),dbc.Col([selectYrA1],width=8)],justify='around') ], width = {'size':6}), 
            dbc.Col([author2Options, dbc.Row([dbc.Col([careerORSingleA2],width=4),dbc.Col([selectYrA2],width=8)],justify='around') ], width = {'size':6}), 
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'InfoAuthor1' + SUFFIX), width = {'size':6}), dbc.Col(html.Center(id = 'InfoAuthor2' + SUFFIX), width = {'size':6})
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'FieldAuthor1' + SUFFIX), width = {'size':6}), dbc.Col(html.Center(id = 'FieldAuthor2' + SUFFIX), width = {'size':6})
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'CountryAuthor1' + SUFFIX), width = {'size':6}), dbc.Col(html.Center(id = 'CountryAuthor2' + SUFFIX), width = {'size':6})
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'InstitutionAuthor1' + SUFFIX), width = {'size':6}), dbc.Col(html.Center(id = 'InstitutionAuthor2' + SUFFIX), width = {'size':6})
        ])
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
    # =============== Figure title
    #figTitle = html.Div(' ', id = 'figTitleCard' + SUFFIX, style = {'color':lightAccent1, 'font-size':25})
    # =============== C score figure
    metricsFigAuthor_c = dbc.Row([dbc.Col([html.Center(dcc.Graph(id = 'metricsFigGraphAuthor_c' + SUFFIX, figure = empty_fig, config = {'displayModeBar': False}))], width = {'offset':1, 'size':2}), dbc.Col(id = 'c_score_formula' + SUFFIX, width = 7)])
    # =============== Figure callbacks
    @callback(
        Output('2author_figs' + SUFFIX, 'children'), 
        Output('metricsFigGraphAuthor_c' + SUFFIX, 'figure'), 
        Output('c_score_formula' + SUFFIX, 'children'),
        Input('careerORSingleYrA1' + SUFFIX, 'value'),
        Input('selectYrRadioA1' + SUFFIX,'value'),
        Input('careerORSingleYrA2' + SUFFIX, 'value'),
        Input('selectYrRadioA2' + SUFFIX,'value'),
        Input('selfCToggle' + SUFFIX, 'on'), 
        Input('logTransfToggleMain' + SUFFIX, 'on'),
        State('author1OptionsDropdown' + SUFFIX, 'value'), 
        State('author2OptionsDropdown' + SUFFIX, 'value'), 
        # Input('ncSlider1' + SUFFIX, 'value'), Input('hSlider1' + SUFFIX, 'value'), Input('hmSlider1' + SUFFIX, 'value'), 
        # Input('ncsSlider1' + SUFFIX, 'value'), Input('ncsfSlider1' + SUFFIX, 'value'), Input('ncsflSlider1' + SUFFIX, 'value'), 
        # Input('ncSlider2' + SUFFIX, 'value'), Input('hSlider2' + SUFFIX, 'value'), Input('hmSlider2' + SUFFIX, 'value'), 
        # Input('ncsSlider2' + SUFFIX, 'value'), Input('ncsfSlider2' + SUFFIX, 'value'), Input('ncsflSlider2' + SUFFIX, 'value'),
        #Input('ncWDD' + SUFFIX, 'value'), Input('hWDD' + SUFFIX, 'value'), Input('hmWDD' + SUFFIX, 'value'),
        #Input('ncsWDD' + SUFFIX, 'value'), Input('ncsfWDD' + SUFFIX, 'value'), Input('ncsflWDD' + SUFFIX, 'value')
        )
    # nc1, h1, hm1, ncs1, ncsf1, ncsfl1, nc2, h2, hm2, ncs2, ncsf2, ncsfl2
    def update_author_figs_and_rank(career1, yr1, career2, yr2, ns, logTransf,group1_name, group2_name): # weights: ncW, hW, hmW, ncsW, ncsfW, ncsflW):
        '''
        group1_name: author name
        group2_name: author name
        '''
        if career1 == None or yr1 == None or career2 == None or yr2 == None: raise PreventUpdate
        elif group1_name == None and group2_name == None: return ["No dataset selected"] + [''] + [empty_fig] + ['']
        else:

            prefix1 = 'career' if career1 else 'singleyr'
            results = get_es_results(group1_name, prefix1, 'authfull')
            data1 = {}
            data1_log = {}
            if results is not None:
                data1 = es_result_pick(results, 'data', None)
                data1_log  = data1[f'{prefix1}_{yr1}_log']
                data1 =  data1[f'{prefix1}_{yr1}']

            prefix2 = 'career' if career2 else 'singleyr'
            results = get_es_results(group2_name, prefix2, 'authfull')
            data2 = {}
            data2_log = {}
            if results is not None:
                data2 = es_result_pick(results, 'data', None)
                data2_log  = data2[f'{prefix2}_{yr2}_log']
                data2 =  data2[f'{prefix2}_{yr2}']

        # if career2 == True:
        #     dfs = dfs_career.copy()
        #     dfs_log = dfs_career_log.copy()
        # else:
        #     dfs = dfs_singleyr.copy()
        #     dfs_log = dfs_singleyr_log.copy()

            fig_list, new_rank_1, new_rank_2 = main_2_author_figs(data1, data1_log, data2, data2_log, group1_name, group2_name, ns, logTransf, g1c = g1c, g2c = g2c, 
                #author1_metrics = {'nc': nc1, 'h': h1, 'hm': hm1, 'ncs': ncs1, 'ncsf': ncsf1, 'ncsfl': ncsfl1}, 
                author1_metrics = {},
                author2_metrics = {})
            for i in range(6): fig_list[i].update_layout(height = 200,width=200)
            fig_list[6].update_layout(height = 230, margin = {'t':20})

            # Title
            title = 'Ranking based on composite score C and bar plots of metrics used to compute C'

            # =============== Author 1 LEDD Display
            rankAuthor1_label = 'Rank of ' + group1_name if group1_name != None else 'No author selected'
            rankAuthor1 = daq.LEDDisplay(label = {"label":rankAuthor1_label, "style":{"color":highlight1, "font-size":"16px"}}, value = new_rank_1, backgroundColor = darkAccent1, color = highlight1, size = 70)
            
            # =============== Author 2 LEDD Display
            rankAuthor2_label = 'Rank of ' + group2_name if group2_name != None else 'No author selected'
            rankAuthor2 = daq.LEDDisplay(label = {"label":rankAuthor2_label, "style":{"color":highlight2, "font-size":"16px"}}, value = new_rank_2, backgroundColor = darkAccent1, color = highlight2, size = 70)

            # =============== N authors display
            # Not needed, complicated.
            #info  = pd.read_json('cumulative_summary.json')
            #N_authors = daq.LEDDisplay(label = {"label":'Number of authors', "style":{"color":darkAccent2, "font-size":"16px"}}, value = int(info['total']), backgroundColor = darkAccent1, color = darkAccent2, size = 40)

            figures = dbc.Row([
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[0]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[1]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[2]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[3]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[4]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[5]))], width = 2)]),
            c_img = dbc.Container([dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row([dbc.Col(rankAuthor1), dbc.Col(rankAuthor2)]), dbc.Row(html.Br()), dbc.Row(html.Img(src = 'assets/c_formula.png', style = {'width':1000}))])
            return(figures, fig_list[6], c_img)

    def main_2_author_figs(df_in, df_in_log, df2_in, df2_in_log, group1_name, group2_name, ns, logTransf, g1c = ['lightcoral', 'red'], g2c = ['lightblue', 'blue'], author1_metrics = {}, author2_metrics = {}, weights = [1, 1, 1, 1, 1, 1]):
        metrics_list = ['nc (ns)', 'h (ns)', 'hm (ns)',  'ncs (ns)', 'ncsf (ns)', 'ncsfl (ns)', 'c (ns)'] if ns else ['nc', 'h', 'hm',  'ncs', 'ncsf', 'ncsfl', 'c' ]
        
        if ns:
            cname  = 'c (ns)'
            rname  = 'rank (ns)'
        else:
            cname  = 'c'
            rname  = 'rank'
        
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

        # Get author 2 metrics to plot
        if group2_name != None:
            metrics_dict = get_initial_metrics_list(df2_in, group2_name, ns)
            metrics_dict_log = get_initial_metrics_list(df2_in_log, group2_name, ns)
            for key, value in author2_metrics.items():
                if ns: key += ' (ns)'
                metrics_dict[key] = value
            new_rank_2 = df2_in[rname]

            new_y_values_2 = list(metrics_dict.values())
            new_y_values_2.append(df2_in[cname])
            new_y_values_2_log = list(metrics_dict_log.values())
            new_y_values_2_log.append(df2_in_log[cname])

            # new_y_values_2 = list(metrics_dict.values()).append(df2_in['c'])
            # new_y_values_2_log = list(metrics_dict_log.values()).append(df2_in_log['c'])
            # _, new_rank_2, new_y_values_2, _ = update_c_and_rank(df2_in, author = group2_name, metrics_dict = metrics_dict, ns = ns, logTransf = False, weights = weights)
            # _, _, new_y_values_2_log, _ = update_c_and_rank(df2_in, author = group2_name, metrics_dict = metrics_dict, ns = ns, logTransf = True, weights = weights)
        else:
            new_rank_2 = 0
            new_y_values_2 = [0]*7
            new_y_values_2_log = [0]*7

        def make_bar_traces(fig, y_in, y_in_log, colors, metric, name, logTransf = False, group_num = 1):
            if logTransf and metric != 'c' and metric != 'c (ns)': fig.add_trace(go.Bar(name = name, x = [metric], y = [y_in_log], text = [y_in], textposition = 'auto',marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
            else: fig.add_trace(go.Bar(name = name, x = [metric], y = [y_in], text = [y_in], textposition = 'auto',marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
            hovertemp = 'count: %{text:.4s}<extra></extra> '
            fig.update_traces(texttemplate = '%{text:.2s}', hovertemplate = hovertemp)
            fig.update_layout(showlegend=False)
            return(fig)
        
        # metric titles
        subplot_titles = ['Number of citations<br>(NC)', 'H-index<br>(H)', 'Hm-index<br>(Hm)', 'Number of citations to<br>single authored papers<br>(NCS)', 
            'Number of citations to<br>single and first<br>authored papers<br>(NCSF)', 'Number of citations to<br>single, first and<br>last authored papers<br>(NCSFL)', 'Composite score (C)']
        fig_list = []
        for i, m in enumerate(metrics_list):
            # subplot_title = get_metric_long_name(career, yr, m) --> problem: gets out of margin
            if group1_name != None and group2_name == None: # If Author 1 only
                fig = make_subplots(rows = 1, cols = 1)
                fig = make_bar_traces(fig, y_in = new_y_values_1[i], y_in_log = new_y_values_1_log[i], colors = g1c, metric = m, name = group1_name, logTransf = logTransf, group_num = 1)
            if group1_name == None and group2_name != None: # If Author 2 only
                fig = make_subplots(rows = 1, cols = 1)
                fig = make_bar_traces(fig, y_in = new_y_values_2[i], y_in_log = new_y_values_2_log[i], colors = g2c, metric = m, name = group2_name, logTransf = logTransf, group_num = 1)
            else: # If Author 1 and Author 2 exist
                fig = make_subplots(rows = 1, cols = 2, column_widths = [0.5, 0.5], shared_yaxes = True, horizontal_spacing = 0)
                fig = make_bar_traces(fig, y_in = new_y_values_1[i], y_in_log = new_y_values_1_log[i], colors = g1c, metric = m, name = group1_name, logTransf = logTransf, group_num = 1) 
                fig = make_bar_traces(fig, y_in = new_y_values_2[i], y_in_log = new_y_values_2_log[i], colors = g2c, metric = m, name = group2_name, logTransf = logTransf, group_num = 2)
            fig.update_layout(height = 500, title_x = 0.5, title_y = 0.95, title = {'text':subplot_titles[i], 'font':{'size':14}}, font = {'size':12, 'color':lightAccent1},
                plot_bgcolor = bgc, paper_bgcolor = bgc, margin = {'l':10, 'r':5, 'b':0, 't':100})
            # if logTransf and m != 'c' and m != 'c (ns)':
            #     max_m_log = max([df_in_log[m].max(), new_y_values_1_log[i], new_y_values_2_log[i]])
            #     max_m = max([df_in[m].max(), new_y_values_1[i], new_y_values_2[i]])
            #     if i == 6: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, range = [0, max_m]) # do not log-transform C score y-axis
            #     else: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2,
            #         tickvals = [k*(max_m_log/6) for k in range(0,6)],
            #         ticktext = [int(np.exp(k*(max_m_log/6)*(np.log(max_m + 1)))) for k in range(0,6)],
            #         range = [0, max_m_log])
            # else: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, range = [0, df_in[m].max()])
            fig.update_xaxes(automargin = True, showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, tickmode = "array", tickvals = [])
            fig.update_layout(showlegend=False)
            fig_list.append(fig)
        return(fig_list, new_rank_1, new_rank_2)

    offcanvas2 = html.Div(
        [
            dbc.Offcanvas(
                dcc.Markdown(
                    '''
                * **User interactions**
                    * `Toggle 1`: Compare metrics using a logarithmic scale.
                    * `Toggle 2`: Choose to exclude or include author self-citations.
                    * Data type and year selection options will be enabled based on the selected researcher.
                    * Users can compare different years and dataset types between two researchers.
                * **Notes**
                    * Rankings are determined by the composite score C, alongside bar plots illustrating the metrics utilized to calculate C. Scores are retrieved from the Elsevier database corresponding to the chosen year/dataset type.
                    * Researcher metrics can span their entire career (career) or be specific to a single year of interest (single year).
                    * Single-year data is unavailable for 2018 for all researchers.
                * **Other**
                    * The np (number of papers) appears to be inconsistent with the selected data type.
                    '''
                ),
                id="offcanvas2",
                title="Compare top 2% researchers",
                is_open=False,
            ),
        ]
    )

    @callback(
        Output("offcanvas2", "is_open"),
        Input("open-offcanvas2", "n_clicks"),
        [State("offcanvas2", "is_open")],
    )
    def toggle_offcanvas(n1, is_open):
        if n1:
            return not is_open
        return is_open

    row3 = html.Div([
        dbc.Row(html.Br()), 
        dbc.Row([dbc.Col(logTransf, width = {'offset':4, 'size':2}), dbc.Col(selfC, width = {'size':2}),dbc.Col(dbc.Button("ℹ️ More info", id="open-offcanvas2", n_clicks=0),width = {'size':2})]), 
        dbc.Row(html.Br()), 
        metricsFigAuthor_c,
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
            html.Hr(), 
            row2, 
            html.Hr(), 
            dls.GridFade(row3,color="#ECAB4C"), 
        ], style = {'backgroundColor':darkAccent1}), 
    ]))