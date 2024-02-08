
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
from plotly.validators.scatter.marker import SymbolValidator
import country_converter as coco

# =============== Plotly Dash libraries
import dash
from dash import html, dcc, callback, ctx #, Input, Output
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq
import dash_loading_spinners as dls

# =============== Custom lib
from citations_lib.create_fig_helper_functions import *
from citations_lib.utils import *
from citations_lib.callback_templates import *

def author_vs_group_layout():
    # ========================================================================================== 
    # ========================================================================================== 
    # Data Preparation
    # ========================================================================================== 
    # ========================================================================================== 
    #dfs_career, dfs_singleyr, dfs_career_log, dfs_singleyr_log, dfs_career_text, dfs_singleyr_text, dfs_career_yrs, dfs_singleyr_yrs = load_standardized_data()
    dropdown_opts = dict()
    for i in range(5):
        with open(f'aggregate/info_career_{i}.pkl', 'rb') as fp: info = pickle.load(fp)
        dropdown_opts['career ' + str(i)] = info
    for i in range(4):
        with open(f'aggregate/info_singleyr_{i}.pkl', 'rb') as fp: info = pickle.load(fp)
        dropdown_opts['singleyr ' + str(i)] = info

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
    theme =  {'dark': True, 'detail': lightAccent1, 'primary': darkAccent1, 'secondary': lightAccent1 }

    g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
    g2c = [highlight2, darkAccent3] # bar plot bar 3
    bgc = darkAccent1 # bar plot background

    layout = html.Div([
        dbc.Container(fluid = True, children = [
            dbc.Row(html.Br()),
        ], style = {'backgroundColor':darkAccent1}), 
    ])

    SUFFIX = '_author_vs_group'

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 1: select dataset!
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Card: 'Select dataset'
    selectStep1 = dbc.Card(dbc.CardBody(html.Center("Select dataset", style = {'color':darkAccent3, 'font-size':20})),color = darkAccent2)

    # =============== Career vs Singleyr
    careerORSingleYr = html.Div([
        dbc.RadioItems(id = "careerORSingleYrRadio" + SUFFIX, value = True, className = "btn-group", inputClassName = "btn-check", labelClassName = "btn btn-outline-primary",
            labelCheckedClassName = "active", options = [{"label": "Career", "value": True}, {"label": "Single year", "value": False}, 
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

    # =============== Year

    single_yr_convention = {"2017":0,"2019":1,"2020":2,"2021":3}
    career_yr_convention = {"2017":0,"2018":1,"2019":2,"2020":3,"2021":4}
    # def update_yr_options(career):
    #     if career == False: return [{"label": "2017", "value": 0, 'disabled': False}, {"label": "2018", 'disabled': True}, {"label": "2019", "value": 1, 'disabled': False}, 
    #         {"label": "2020", "value": 2, 'disabled': False}, {"label": "2021", "value": 3, 'disabled': False}]
    #     else: return [{"label": "2017", "value": 0, 'disabled': False}, {"label": "2018", "value": 1, 'disabled': False}, 
    #         {"label": "2019", "value": 2, 'disabled': False}, {"label": "2020", "value": 3, 'disabled': False}, {"label": "2021", "value": 4, 'disabled': False}]
    # selectYr = html.Div(
    #     [dbc.RadioItems(
    #         value = 3, id = "selectYrRadio" + SUFFIX, className = "btn-group", inputClassName = "btn-check", 
    #         labelClassName = "btn btn-outline-primary", labelCheckedClassName = "active", style = {'size':'sm'}, 
    #         options = update_yr_options(career = True))
    # ], className = "radio-group")
    # @callback(
    #     Output('selectYrRadio' + SUFFIX, 'options'), 
    #     Input('careerORSingleYrRadio' + SUFFIX, 'value'))
    # def update_yr_opts(career):
    #     return(update_yr_options(career))

    # row1 = dbc.Row([dbc.Col(html.Center(selectStep1), width = {'offset':1,'size':3}), 
    #         dbc.Col(html.Center(careerORSingleYr), width = 2), 
    #         dbc.Col(html.Center(selectYr), width = 4)])

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 2 Select groups
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Group 1 (author) Dropdown

    group1List = dcc.Dropdown(options = [], placeholder = 'Author 1: Start typing name and surname', multi = False, id = "group1ListDropdown" + SUFFIX, 
    value = 'Ioannidis, John P.A.', searchable = True)
    generate_es_dropdown_callback("group1ListDropdown" + SUFFIX)
    generate_update_carsing_callback('group1ListDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX)
    generate_update_years_callback('careerORSingleYrA1' + SUFFIX, 'selectYrRadioA1' + SUFFIX, 'group1ListDropdown' + SUFFIX)
    output_ids = ['InfoAuthor1' + SUFFIX, 'FieldAuthor1' + SUFFIX, 'CountryAuthor1' + SUFFIX, 'InstitutionAuthor1' + SUFFIX]
    generate_update_cards_callback('selectYrRadioA1' + SUFFIX, output_ids, 'group1ListDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX,darkAccent1, highlight1)

    # group1List = dcc.Dropdown(id = "group1ListDropdown" + SUFFIX, 
    #     options = ['Author'], multi = False, searchable = True)
    # group1ListOptions = dcc.Dropdown(options = ['Search authors'], placeholder = 'Step 2: Select Author', multi = False, id = "group1ListOptionsDropdown" + SUFFIX, 
    #     value = 'Ioannidis, John P.A.', searchable = True)
    # @callback(
    #     Output('group1ListOptionsDropdown' + SUFFIX, 'options'), 
    #     Output('group1ListDropdown' + SUFFIX, 'value'), 
    #     Input('careerORSingleYrRadio' + SUFFIX, 'value'), 
    #     Input('selectYrRadio' + SUFFIX, 'value'), 
    #     Input('group1ListOptionsDropdown' + SUFFIX, 'search_value'))
    # def update_Author1Dropdown(career, yr, search_value):
    #     if career == None or yr == None or not search_value: raise PreventUpdate
    #     else:
    #         f_out = 'career' if career == True else 'singleyr'
    #         optns = dropdown_opts[f_out + ' ' + str(yr)]['authfull']
    #         optns_dd = [{'label':name, 'value':name} for name in optns] # dynamic dropdown to speed things up
    #         return [o for o in optns_dd if search_value in o["label"]], 'Author'
    # =============== Group 1 (author) Callback
    # @callback(
    #     Output('InfoAuthor1' + SUFFIX, 'children'), 
    #     Output('FieldAuthor1' + SUFFIX, 'children'), 
    #     Output('CountryAuthor1' + SUFFIX, 'children'), 
    #     Output('InstitutionAuthor1' + SUFFIX, 'children'), 
    #     Input('careerORSingleYrRadio' + SUFFIX, 'value'), 
    #     Input('selectYrRadio' + SUFFIX, 'value'), 
    #     Input('group1ListDropdown' + SUFFIX, 'value'))
    # def update_Author1(career, yr, value):
    #     if value == None: raise PreventUpdate
    #     else:
    #         if career == True:
    #             dfs = dfs_career.copy()
    #         else:
    #             dfs = dfs_singleyr.copy()
    #         field = dfs[yr][dfs[yr]['authfull'] == value]['sm-field'].values[0]
    #         cntry = dfs[yr][dfs[yr]['authfull'] == value]['cntry'].values[0]
    #         inst = dfs[yr][dfs[yr]['authfull'] == value]['inst_name'].values[0]
    #         cntry_full = coco.convert(names = cntry, to = 'name_short')
    #         card1 = dbc.Card(html.Center('Author: ' + value + ' (' + str(int(round(dfs[yr][dfs[yr]['authfull'] == value]['self%'].values[0], 2)*100)) + ' % self-citation)', style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
    #         card2 = dbc.Card(html.Center(field + ' (' + str(int(round(dfs[yr][dfs[yr]['sm-field'] == field]['self%'].mean(), 2)*100)) + ' % mean self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight1)
    #         card3 = dbc.Card(html.Center(cntry_full + ' (' + str(int(round(dfs[yr][dfs[yr]['cntry'] == cntry]['self%'].mean(), 2)*100)) + ' % mean self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight1)
    #         card4 = dbc.Card(html.Center(inst + ' (' + str(int(round(dfs[yr][dfs[yr]['inst_name'] == inst]['self%'].mean(), 2)*100)) + ' % mean self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight1)
    #         return(card1, card2, card3, card4)

    # =============== Group 2 Dropdowns
    group2List = dcc.Dropdown(id = "group2ListDropdown" + SUFFIX, 
        placeholder = 'Step 3: Select Group 2', multi = False, searchable = True, value = 'sm-field', style = {'background-color':darkAccent3},
        options = [{'label':'Country', 'value': 'cntry'}, {'label':'Field', 'value': 'sm-field'}, {'label':'Institution', 'value': 'inst_name'}])
    group2ListOptions = dcc.Dropdown(id = "group2ListOptionsDropdown" + SUFFIX,value = 'Clinical Medicine', searchable = True, style = {'background-color':darkAccent3})
    # =============== Group 2 Callbacks
    @callback(
        Output('group2ListOptionsDropdown' + SUFFIX, 'options'), Output('group2ListOptionsDropdown'+ SUFFIX, 'placeholder'), 
        Input('careerORSingleYrA1'+ SUFFIX, 'value'), Input('selectYrRadioA1'+ SUFFIX, 'value'), 
        Input('group2ListDropdown'+ SUFFIX, 'value'), Input('group2ListOptionsDropdown'+ SUFFIX, 'search_value'))
    def update_group_2_dropdown_options(career, yr, value, search_value):
        if career == None or yr == None or not value: raise PreventUpdate
        if value == 'all': return ['All authors selected'], 'All authors selected'
        else:

            # This is needed to get the idx-like year
            if career:
                yr = career_yr_convention[yr]
            else:
                yr = single_yr_convention[yr]

            f_out = 'career' if career == True else 'singleyr'
            optns = dropdown_opts[f_out+' '+str(yr)][value]
            optns = [x for x in optns if x != 'Nan']
            if value == 'inst_name': # dynamic dropdown to speed things up for institutions (too many options)
                if search_value == None: raise PreventUpdate
                else:
                    optns_dd = [{'label':name, 'value':name} for name in optns]
                    return [o for o in optns_dd if search_value in o["label"]], 'Select institution'
            elif value == 'cntry': # important to display full country names
                optns_names = dropdown_opts[f_out+' '+str(yr)]['cntry_full']
                return [{'label':name, 'value':value} for name, value in zip(optns_names, optns)], 'Select country' #return [{'label':coco.convert(names = name, to = 'name_short'), 'value':name} for name in optns], 'Select country'
            else: return [{'label':name, 'value':name} for name in optns], 'Select field'
    
    @callback(
        Output('Group2Title'+ SUFFIX, 'children'), Output('Group2Info'+ SUFFIX, 'children'), 
        Input('careerORSingleYrA1' + SUFFIX, 'value'), Input('selectYrRadioA1' + SUFFIX, 'value'), 
        Input('group2ListDropdown'+ SUFFIX, 'value'), Input('group2ListOptionsDropdown'+ SUFFIX, 'value'))
    def update_group_2_dropdown_values(career, yr, group, group_name):
        if career == None or yr == None or group == None: raise PreventUpdate
        else:
            prefix1 = 'career' if career else 'singleyr'
            data = get_es_aggregate(group,group_name,prefix1)
            self_cit = np.round(data[f'{prefix1}_{yr}']['self%'][2]*100,2)

            if group == 'all':
                # This is never the case.
                card1 = dbc.Card(html.Center('Group: All', style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                #card2 = dbc.Card(html.Center('All authors' + ' (' + str(int(round(dfs[yr]['self%'].mean(), 2)*100)) + ' % mean self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
            elif group_name == None: raise PreventUpdate
            else: 
                if group == 'cntry': 
                    title = 'Country'
                    card1 = dbc.Card(html.Center('Group: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                    try:
                        card2 = dbc.Card(html.Center(coco.convert(names = group_name, to = 'name_short') + ' (' + str(self_cit) + ' % median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
                    except:
                        card2 = dbc.Card(html.Center('Select a country to start.'), style = {'color':darkAccent1, 'font-size':14}, color = highlight2)
                else:
                    title = 'Field' if group == 'sm-field' else 'Institution'
                    card1 = dbc.Card(html.Center('Group 2: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                    try:
                        card2 = dbc.Card(html.Center(group_name + ' (' + str(self_cit) + ' % median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
                    except:
                        card2 = dbc.Card(html.Center('Please make a selection.'), style = {'color':darkAccent1, 'font-size':14}, color = highlight2)
            return(card1, card2)

    row2 = dbc.Container([
        dbc.Row([
            #dbc.Col([html.Center(group1List),html.Center(group1ListOptions)], width = {'size':6}), 
            dbc.Col([html.Center(group1List), dbc.Row([dbc.Col([careerORSingleA1],width=4),dbc.Col([selectYrA1],width=8)],justify='around') ], width = {'size':6}), 
            dbc.Col([html.Center(group2List),html.Center(group2ListOptions)], width = {'size':6}), 
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'InfoAuthor1' + SUFFIX), width = {'size':6}), 
            dbc.Col(html.Center(id = 'Group2Title' + SUFFIX), width = {'size':6})
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'FieldAuthor1' + SUFFIX), width = {'size':6}), 
            dbc.Col(html.Center(id = 'Group2Info' + SUFFIX), width = {'size':6})
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'CountryAuthor1' + SUFFIX), width = {'size':6})
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'InstitutionAuthor1' + SUFFIX), width = {'size':6})
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
    metricsFig_c = dbc.Row([dbc.Col([html.Center(dcc.Graph(id = 'metricsFigGraphAuthor_c' + SUFFIX, figure = empty_fig, config = {'displayModeBar': False}))], width = {'offset':1, 'size':2}), dbc.Col(id = 'c_score_formula' + SUFFIX, width = 7)])
    # =============== Figure callbacks
    @callback(
        Output('2group_figs' + SUFFIX, 'children'), 
        Output('metricsFigGraphAuthor_c' + SUFFIX, 'figure'), 
        Output('c_score_formula' + SUFFIX, 'children'), 
        #Input('careerORSingleYrRadio' + SUFFIX, 'value'), 
        #Input('selectYrRadio' + SUFFIX, 'value'), 
        Input('group1ListDropdown'+ SUFFIX, 'value'),
        Input('group2ListDropdown'+ SUFFIX, 'value'),
        Input('group2ListOptionsDropdown'+ SUFFIX, 'value'),
        Input('selfCToggle' + SUFFIX, 'on'), 
        Input('logTransfToggleMain' + SUFFIX, 'on'),
        Input('careerORSingleYrA1' + SUFFIX, 'value'),
        Input('selectYrRadioA1' + SUFFIX,'value'))
    def update_group_figures(group1_name, group2, group2_name, ns, logTransf, career1, yr1):
        '''
        group1: author
        group2: all, country, institution, field
        '''
        if career1 == None or yr1 == None: raise PreventUpdate
        elif group1_name == None and group2 != 'all' and group2_name == None: return ["No dataset selected"] + [''] + [empty_fig] + ['']
        else:

            prefix1 = 'career' if career1 else 'singleyr'
            results = get_es_results(group1_name, prefix1, 'authfull')
            data1 = {}
            data1_log = {}
            if results is not None:
                data1 = es_result_pick(results, 'data', None)
                data1_log  = data1[f'{prefix1}_{yr1}_log']
                data1 =  data1[f'{prefix1}_{yr1}']

            data2 = {}
            data2_log = {}
            # copy correct dfs (all were loaded at the beginning)

            # if group2 == 'cntry':
            #     cur_country = coco.convert(names = group2_name, to = 'ISO3')
            #     results = get_es_results(cur_country.lower(),f'{prefix1}_{group2}','cntry',True)
            #     data2 = es_result_pick(results, 'data', None)
            # elif group2 == "sm-field":
            #     results = get_es_results(group2_name,f'{prefix1}_field','sm-field')
            #     data2 = es_result_pick(results, 'data', None)
            # elif group2 == "inst_name":
            #     results = get_es_results(group2_name,f'{prefix1}_inst','inst_name')
            #     data2 = es_result_pick(results, 'data', None)
            data2 = get_es_aggregate(group2,group2_name,prefix1)
            if data2 is not None:
                data2_log  = data2[f'{prefix1}_{yr1}_log']
                data2 =  data2[f'{prefix1}_{yr1}']

            # remove n/a values for 'all' option
            # DISABLED THIS OPTION
            if group2 == 'all': group2_name = 'Dataset'

            fig_list, n1, n2 = main_author_group_figs(data1, data1_log, data2, data2_log, group1_name, group2, group2_name, ns, logTransf, g1c = g1c, g2c = g2c)
            for i in range(6): fig_list[i].update_layout(height = 230)
            fig_list[6].update_layout(height = 250, margin = {'t':40})

            # Title
            title = 'Ranking based on composite score C and bar plots of metrics used to compute C'

            # =============== Group 1 Number of Authors LEDD Display
            authorRank_label = 'Glob. Rank of ' + group1_name if group1_name != None else 'No author selected'
            authorRank = daq.LEDDisplay(label = {"label":authorRank_label, "style":{"color":highlight1, "font-size":"16px"}}, value = n1, backgroundColor = darkAccent1, color = highlight1, size = 70)
            
            # =============== Group 2 Number of Authors LEDD Display
            if group2_name != None: group2_title = coco.convert(names = group2_name, to = 'name_short') if group2 == 'cntry' else group2_name
            nAuthors2_label = 'Number of Authors in ' + group2_title if group2_name != None else 'No group selected'
            nAuthors2 = daq.LEDDisplay(label = {"label":nAuthors2_label, "style":{"color":highlight2, "font-size":"16px"}}, value = n2, backgroundColor = darkAccent1, color = highlight2, size = 70)

            figures = dbc.Row([
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[0]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[1]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[2]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[3]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[4]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[5]))], width = 2)]),
            c_img = dbc.Container([dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row([dbc.Col(authorRank), dbc.Col(nAuthors2)]), dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row(html.Center('Composite score C formula:')), dbc.Row(html.Br()), dbc.Row(html.Img(src = 'assets/c_formula.png', style = {'width':1000}))])
            return(figures, fig_list[6], c_img)

    def main_author_group_figs(df1_in, df1_in_log, df2_in, df2_in_log, group1_name, group2, group2_name, ns, logTransf, g1c = ['lightcoral', 'red'], g2c = ['lightblue', 'blue']):
        '''
        Output:
            7 figures (one per metric involved in calculating composite score C + composite score C)
            Rank of author
            Number of authors in group
        '''
        # threshold which we make bar plot of mean values instead of histogram
        N_min = 10

        # list of metrics
        metrics_list = ['nc (ns)','h (ns)','hm (ns)',  'ncs (ns)', 'ncsf (ns)','ncsfl (ns)','c (ns)'] if ns else ['nc', 'h', 'hm',  'ncs', 'ncsf','ncsfl','c']
        if ns:
            cname  = 'c (ns)'
            rname  = 'rank (ns)'
        else:
            cname  = 'c'
            rname  = 'rank'
        # Get author metrics to plot
        if group1_name != None:
            metrics_dict = get_initial_metrics_list(df1_in, group1_name, ns)
            metrics_dict_log = get_initial_metrics_list(df1_in_log, group1_name, ns)
            new_y_values_1 = list(metrics_dict.values())
            new_y_values_1.append(df1_in[cname])
            new_y_values_1_log = list(metrics_dict_log.values())
            new_y_values_1_log.append(df1_in_log[cname])
            n1 = df1_in[rname]
            # _, n1, new_y_values_1, _ = update_c_and_rank(df_in, author = group1_name, metrics_dict = metrics_dict, ns = ns, logTransf = False)
            # _, _, new_y_values_1_log, _ = update_c_and_rank(df_in, author = group1_name, metrics_dict = metrics_dict, ns = ns, logTransf = True)
        else:
            n1 = 0
            new_y_values_1 = [0]*7
            new_y_values_1_log = [0]*7

        if group2_name != None and df2_in != None:
            metrics_dict = get_initial_metrics_list(df2_in, group2_name, ns)
            metrics_dict_log = get_initial_metrics_list(df2_in_log, group2_name, ns)
            new_y_values_2 = list(metrics_dict.values())
            new_y_values_2.append(df2_in[cname])
            new_y_values_2_log = list(metrics_dict_log.values())
            new_y_values_2_log.append(df2_in_log[cname])
            try:
                n2 = df2_in['c'][5]
            except:
                n2= 0 
            # _, n1, new_y_values_1, _ = update_c_and_rank(df_in, author = group1_name, metrics_dict = metrics_dict, ns = ns, logTransf = False)
            # _, _, new_y_values_1_log, _ = update_c_and_rank(df_in, author = group1_name, metrics_dict = metrics_dict, ns = ns, logTransf = True)
        else:
            n2 = 0
            new_y_values_2 = [0]*7
            new_y_values_2_log = [0]*7

        # Group dataframe
        # if group2 == 'all':
        #     df2 = df_in.copy()
        #     df2_log = df_in_log.copy()
        # elif group2_name != None:
        #     df2 = df_in[df_in[group2] == group2_name]
        #     df2_log = df_in_log[df_in_log[group2] == group2_name]
        #     if df2.shape[0] < N_min: # if sample size too small for histogram
        #         new_y_values_2 = []
        #         new_y_values_2_log = []
        #         for m in metrics_list:
        #             new_y_values_2.append(df2[m].mean())
        #             new_y_values_2_log.append(df2_log[m].mean())
        # n2 = 0 if group2_name == None else df2.shape[0]

        # def make_bar_traces(fig, y_in, y_in_log, colors, metric, name, logTransf = False, group_num = 1):
        #     if logTransf and metric != 'c' and metric != 'c (ns)': fig.add_trace(go.Bar(name = name, x = [metric], y = [y_in_log], text = [y_in], textposition = 'auto',marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
        #     else: fig.add_trace(go.Bar(name = name, x = [metric], y = [y_in], text = [y_in], textposition = 'auto',marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
        #     fig.update_traces(texttemplate = '%{text:.5s}', textposition = 'outside')
        #     return(fig)
        
        # def make_hist_traces(fig, df, df_log, colors, metric, name, logTransf = False, group_num = 1):
        #     hovertemp = 'mean: '+str(round(df[metric].mean(),0))+'<br>'+'std: '+str(round(df[metric].std(),0))+'<br>y: %{x}<br>count: %{y}<extra></extra>'
        #     if logTransf and metric != 'c' and metric != 'c (ns)': fig.add_trace(go.Histogram(name = name,y = df_log[metric],marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
        #     else: fig.add_trace(go.Histogram(name = name,y = df[metric],marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
        #     fig.update_xaxes(row=1, col = 1, autorange="reversed") if group_num == 1 else fig.update_xaxes(row = 1, col =2, autorange=True)
        #     fig.update_traces(row=1, col = group_num, hovertemplate = hovertemp)
        #     return(fig)

        def make_box_traces(fig, df, df_log, colors, metric, name, logTransf = False, group_num = 1):
            if logTransf and metric != 'c' and metric != 'c (ns)':
                fig.add_trace(go.Box(name=name,marker_color=colors[0],hovertext=['Min', 'Median', 'Max']),row = 1, col = group_num)
                fig.update_traces(name=name,q1= [df_log[metric][1]], median= [df_log[metric][2]],
                            q3= [df_log[metric][3]], lowerfence= [df_log[metric][0]],
                            upperfence=[df_log[metric][4]], hoverinfo="y")
                #fig.add_trace(go.Histogram(name = name,y = df_log[metric],marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
            else: 
                fig.add_trace(go.Box(name=name,marker_color=colors[0]),row = 1, col = group_num)
                fig.update_traces(q1= [df[metric][1]], median= [df[metric][2]],
                            q3= [df[metric][3]], lowerfence= [df[metric][0]],
                            upperfence=[df[metric][4]],hoverinfo="y")
                #fig.add_trace(go.Histogram(name = name,y = df[metric],marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
            fig.update_xaxes(row=1, col = 1, autorange="reversed") if group_num == 1 else fig.update_xaxes(row = 1, col =2, autorange=True)
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(showgrid=False)
            return(fig)
        
        # metric titles
        subplot_titles = ['Number of citations<br>(NC)', 'H-index<br>(H)', 'Hm-index<br>(Hm)', 'Number of citations to<br>single authored papers<br>(NCS)', 
            'Number of citations to<br>single and first<br>authored papers<br>(NCSF)', 'Number of citations to<br>single, first and<br>last authored papers<br>(NCSFL)', 'Composite score (C)']
        
        # get figs!
        fig_list = []
        if group2_name != None: group2_legend = coco.convert(names=group2_name, to='name_short') if group2 == 'cntry' else group2_name
        for i, m in enumerate(metrics_list):
            fig = make_subplots(rows = 1, cols = 1)
            logTransf_val = False if i == 6 else logTransf # do not log-transform C-score

            if group2_name != None:
                #if df2_in is not None: fig = make_bar_traces(fig, y_in = new_y_values_2[i], y_in_log = new_y_values_2_log[i], colors = g2c, metric = m, name = group2_legend, logTransf = logTransf_val, group_num = 1)
                fig = make_box_traces(fig, df2_in, df2_in_log, colors = g2c, metric = m, name = group2_legend, logTransf = logTransf_val, group_num = 1)
            else: 
                fig.add_trace(go.Bar(x = [m], y = [0], text = [0], marker_color = g1c[0], marker_line_width = 0), row = 1, col = 1)
            if group1_name != None: 
                if logTransf and m != 'c' and m != 'c (ns)': fig.add_hline(new_y_values_1_log[i], line_color = g1c[0], line_width = 4, annotation_text= 'Author: ' + str(round(new_y_values_1[i],2)), annotation_font_color=g1c[0], annotation_position="top left")
                else: fig.add_hline(new_y_values_1[i], line_color = g1c[0], line_width = 4, annotation_text= 'Author: ' + str(round(new_y_values_1[i],2)), annotation_font_color=g1c[0], annotation_position="top left")
            fig.update_layout(height = 500, title_x = 0.5, title = {'text':subplot_titles[i], 'font':{'size':14}}, font = {'size':12, 'color':lightAccent1}, showlegend = False, 
                plot_bgcolor = bgc, paper_bgcolor = bgc, margin = {'l':10, 'r':5, 'b':0})
            # if logTransf and m != 'c' and m != 'c (ns)':
            #     max_m_log = max([df_in_log[m].max(), new_y_values_1_log[i]])
            #     max_m = max([df_in[m].max(), new_y_values_1[i]])
            #     if i == 6: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, range = [0, max_m]) # do not log-transform C score y-axis
            #     else: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2,
            #         tickvals = [k*(max_m_log/6) for k in range(0,6)],
            #         ticktext = [int(np.exp(k*(max_m_log/6)*(np.log(max_m + 1)))) for k in range(0,6)], range = [0, max_m_log])
            # else: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, range = [0, df_in[m].max()])
            fig.update_xaxes(automargin = True, showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, tickmode = "array", tickvals = [])
            fig_list.append(fig)
        return(fig_list, n1, n2)

    row3 = html.Div([
        dbc.Row(html.Br()), 
        dbc.Row([dbc.Col(logTransf, width = {'offset':4, 'size':2}), dbc.Col(selfC, width = {'size':2})]), 
        dbc.Row(html.Br()), metricsFig_c, dbc.Row(html.Br()), 
        dbc.Row(dbc.Col(dbc.Container(id = '2group_figs' + SUFFIX), width = {'offset':1,'size':10})), dbc.Row(html.Br())])

    # ========================================================================================== 
    # ========================================================================================== 
    # Layout
    # ========================================================================================== 
    # ========================================================================================== 
    return(html.Div([
        dbc.Container(fluid = True, children = [
            html.Br(),
            html.Hr(), 
            row2, 
            html.Hr(), 
            dls.GridFade(row3,color="#ECAB4C"), 
            html.Br(), 
        ], style = {'backgroundColor':darkAccent1})]))