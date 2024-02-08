# ========================================================================================== 
# ========================================================================================== 
# IMPORT LIBRARIES
# ========================================================================================== 
# ========================================================================================== 

# =============== misc libs & modules
import pickle

# =============== Plotly libs & modules
import plotly.graph_objects as go
import country_converter as coco

# =============== Plotly Dash libraries
import dash
from dash import html, dcc, callback #, Input, Output
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq

# =============== Custom lib
from citations_lib.create_fig_helper_functions import *
from citations_lib.utils import *
import dash_loading_spinners as dls

def group_vs_group_layout():
    # ========================================================================================== 
    # ========================================================================================== 
    # Data Preparation
    # ========================================================================================== 
    # ========================================================================================== 

    #dfs_career, dfs_singleyr, dfs_career_log, dfs_singleyr_log, _, _, _, _ = load_standardized_data()

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

    g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
    g2c = [highlight2, darkAccent3] # bar plot bar 3
    bgc = darkAccent1 # bar plot background
    SUFFIX = '_group_vs_group'

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 1: select dataset!
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Select dataset!
    selectStep1 = dbc.Card(dbc.CardBody(html.Center("Select dataset", style = {'color':darkAccent3, 'font-size':20})),color = darkAccent2)

    # =============== Career vs Singleyr
    careerORSingleYr = html.Div([
        dbc.RadioItems(id = "careerORSingleYrRadio" + SUFFIX, value = True, className = "btn-group", inputClassName = "btn-check", labelClassName = "btn btn-outline-primary",
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
            id = "selectYrRadio" + SUFFIX, className = "btn-group", inputClassName = "btn-check", 
            labelClassName = "btn btn-outline-primary", labelCheckedClassName = "active", style = {'size':'sm'}, 
            options = update_yr_options(career = True), value = 3)
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
    # Row 2 Select groups
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Group 1 Dropdowns
    group1List = dcc.Dropdown(id = "group1ListDropdown" + SUFFIX, 
        placeholder = 'Step 2: Select Group 1', multi = False, value = 'sm-field', searchable = True,
        options = [{'label':'All', 'value': 'all'}, {'label':'Country', 'value': 'cntry'}, {'label':'Field', 'value': 'sm-field'}, {'label':'Institution', 'value': 'inst_name'}])
    group1ListOptions = dcc.Dropdown(id = "group1ListOptionsDropdown" + SUFFIX,value = 'Clinical Medicine', searchable = True)
    # =============== Group 1 Callbacks
    @callback(
        Output('group1ListOptionsDropdown' + SUFFIX, 'options'), Output('group1ListOptionsDropdown'+ SUFFIX, 'placeholder'), 
        Input('careerORSingleYrRadio'+ SUFFIX, 'value'), Input('selectYrRadio'+ SUFFIX, 'value'), 
        Input('group1ListDropdown'+ SUFFIX, 'value'), Input('group1ListOptionsDropdown'+ SUFFIX, 'search_value'))
    def update_group_1_dropdown_options(career, yr, value, search_value):
        if career == None or yr == None or not value: raise PreventUpdate
        if value == 'all': return [], 'All authors selected'
        else: 
            f_out = 'career' if career == True else 'singleyr'
            optns = dropdown_opts[f_out+' '+str(yr)][value]
            if value == 'inst_name': # dynamic dropdown to speed things up for institutions (too many options)
                if search_value == None: raise PreventUpdate
                else:
                    optns_dd = [{'label':name, 'value':name} for name in optns]
                    return [o for o in optns_dd if search_value in o["label"]], 'Select institution'
            elif value == 'cntry': # important to display full country names
                optns_names = dropdown_opts[f_out+' '+str(yr)]['cntry_full']
                return [{'label':name, 'value':value} for name, value in zip(optns_names, optns)], 'Select country' # return [{'label':coco.convert(names = name, to = 'name_short'), 'value':name} for name in optns], 'Select country'
            else: return [{'label':name, 'value':name} for name in optns], 'Select field'
    @callback(
        Output('Group1Title'+ SUFFIX, 'children'), Output('Group1Info'+ SUFFIX, 'children'), 
        Input('careerORSingleYrRadio' + SUFFIX, 'value'), Input('selectYrRadio' + SUFFIX, 'value'), 
        Input('group1ListDropdown'+ SUFFIX, 'value'), Input('group1ListOptionsDropdown'+ SUFFIX, 'value'))
    def update_group_1_dropdown_values(career, yr, group, group_name):
        if career == None or yr == None or group == None: raise PreventUpdate
        else:
            if not career:
                yr_convention_r = {"0":"2017","1":"2019","2":"2020","3":"2021"}
            else:
                yr_convention_r = {"0":"2017","1":"2018","2":"2019","3":"2020","4":"2021"}
           
            prefix = 'career' if career else 'singleyr'
            data = get_es_aggregate(group,group_name,prefix)
            self_cit = np.round(data[f'{prefix}_{yr_convention_r[str(yr)]}']['self%'][2]*100,2)
            #get_violin_compare(in1,in2,N1,N2)

            # if career == True: dfs = dfs_career.copy()
            # else: dfs = dfs_singleyr.copy()
            if group == 'all': 
                # Never the case
                card1 = dbc.Card(html.Center('Group 1: All', style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
                card2 = dbc.Card(html.Center('All authors' + ' (' + str(int(round(dfs[yr]['self%'].mean(), 2)*100)) + ' % mean self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight1)
            elif group_name == None: raise PreventUpdate
            else: 
                if group == 'cntry': 
                    title = 'Country'
                    card1 = dbc.Card(html.Center('Group 1: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
                    card2 = dbc.Card(html.Center(coco.convert(names = group_name, to = 'name_short') + ' (' + str(self_cit) + ' % median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight1)
                else:
                    title = 'Field' if group == 'sm-field' else 'Institution'
                    card1 = dbc.Card(html.Center('Group 1: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
                    card2 = dbc.Card(html.Center(group_name + ' (' + str(self_cit) + ' % median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight1)
            return(card1, card2)

    # =============== Group 2 Dropdowns
    group2List = dcc.Dropdown(id = "group2ListDropdown" + SUFFIX, 
        placeholder = 'Step 3: Select Group 2', multi = False, value = 'cntry', searchable = True,
        options = [{'label':'All', 'value': 'all'}, {'label':'Country', 'value': 'cntry'}, {'label':'Field', 'value': 'sm-field'}, {'label':'Institution', 'value': 'inst_name'}])
    group2ListOptions = dcc.Dropdown(id = "group2ListOptionsDropdown" + SUFFIX,value = 'usa', searchable = True)
    # =============== Group 2 Callbacks
    @callback(
        Output('group2ListOptionsDropdown' + SUFFIX, 'options'), Output('group2ListOptionsDropdown'+ SUFFIX, 'placeholder'), 
        Input('careerORSingleYrRadio'+ SUFFIX, 'value'), Input('selectYrRadio'+ SUFFIX, 'value'), 
        Input('group2ListDropdown'+ SUFFIX, 'value'), Input('group2ListOptionsDropdown'+ SUFFIX, 'search_value'))
    def update_group_2_dropdown_options(career, yr, value, search_value):
        if career == None or yr == None or not value: raise PreventUpdate
        if value == 'all': return ['All authors selected'], 'All authors selected'
        else: 
            f_out = 'career' if career == True else 'singleyr'
            optns = dropdown_opts[f_out+' '+str(yr)][value]
            if value == 'inst_name': # dynamic dropdown to speed things up for institutions (too many options)
                if search_value == None: raise PreventUpdate
                else:
                    optns_dd = [{'label':name, 'value':name} for name in optns]
                    return [o for o in optns_dd if search_value in o["label"]], 'Select institution'
            elif value == 'cntry': # important to display full country names
                optns_names = dropdown_opts[f_out+' '+str(yr)]['cntry_full']
                return [{'label':name, 'value':value} for name, value in zip(optns_names, optns)], 'Select country' # return [{'label':coco.convert(names = name, to = 'name_short'), 'value':name} for name in optns], 'Select country'
            else: return [{'label':name, 'value':name} for name in optns], 'Select field'
    @callback(
        Output('Group2Title'+ SUFFIX, 'children'), Output('Group2Info'+ SUFFIX, 'children'), 
        Input('careerORSingleYrRadio' + SUFFIX, 'value'), Input('selectYrRadio' + SUFFIX, 'value'), 
        Input('group2ListDropdown'+ SUFFIX, 'value'), Input('group2ListOptionsDropdown'+ SUFFIX, 'value'))
    def update_group_2_dropdown_values(career, yr, group, group_name):
        if career == None or yr == None or group == None: raise PreventUpdate
        else:
            # if career == True: dfs = dfs_career.copy()
            # else: dfs = dfs_singleyr.copy()
            if not career:
                yr_convention_r = {"0":"2017","1":"2019","2":"2020","3":"2021"}
            else:
                yr_convention_r = {"0":"2017","1":"2018","2":"2019","3":"2020","4":"2021"}
           
            prefix = 'career' if career else 'singleyr'
            data = get_es_aggregate(group,group_name,prefix)
            self_cit = np.round(data[f'{prefix}_{yr_convention_r[str(yr)]}']['self%'][2]*100,2)
            
            if group == 'all': 
                card1 = dbc.Card(html.Center('Group 2: All', style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                #card2 = dbc.Card(html.Center('All authors' + ' (' + str(int(round(dfs[yr]['self%'].mean(), 2)*100)) + ' % mean self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
            elif group_name == None: raise PreventUpdate
            else: 
                if group == 'cntry': 
                    title = 'Country'
                    card1 = dbc.Card(html.Center('Group 2: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                    card2 = dbc.Card(html.Center(coco.convert(names = group_name, to = 'name_short') + ' (' + str(self_cit) + ' % median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
                else:
                    title = 'Field' if group == 'sm-field' else 'Institution'
                    card1 = dbc.Card(html.Center('Group 2: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                    card2 = dbc.Card(html.Center(group_name + ' (' + str(self_cit) + ' % median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
            return(card1, card2)

    row2 = dbc.Container([
        dbc.Row([
            dbc.Col([html.Center(group1List),html.Center(group1ListOptions)], width = {'size':6}), 
            dbc.Col([html.Center(group2List),html.Center(group2ListOptions)], width = {'size':6}), 
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'Group1Title' + SUFFIX), width = {'size':6}), 
            dbc.Col(html.Center(id = 'Group2Title' + SUFFIX), width = {'size':6})
        ]), dbc.Row([
            dbc.Col(html.Center(id = 'Group1Info' + SUFFIX), width = {'size':6}), 
            dbc.Col(html.Center(id = 'Group2Info' + SUFFIX), width = {'size':6})
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
        Input('careerORSingleYrRadio' + SUFFIX, 'value'), 
        Input('selectYrRadio' + SUFFIX, 'value'), 
        Input('group1ListDropdown'+ SUFFIX, 'value'),
        Input('group1ListOptionsDropdown'+ SUFFIX, 'value'),
        Input('group2ListDropdown'+ SUFFIX, 'value'),
        Input('group2ListOptionsDropdown'+ SUFFIX, 'value'),
        Input('selfCToggle' + SUFFIX, 'on'), 
        Input('logTransfToggleMain' + SUFFIX, 'on'))
    def update_group_figures(career, yr, group1, group1_name, group2, group2_name, ns, logTransf):
        '''
        group1: all, country, institution, field
        group2: all, country, institution, field
        '''
        if career == None or yr == None: raise PreventUpdate
        elif group1 != 'all' and group1_name == None and group2 != 'all' and group2_name == None: return ["No dataset selected"] + [''] + [empty_fig] + ['']
        else:
            
            prefix = 'career' if career else 'singleyr'
            if not career:
                yr_convention_r = {"0":"2017","1":"2019","2":"2020","3":"2021"}
            else:
                yr_convention_r = {"0":"2017","1":"2018","2":"2019","3":"2020","4":"2021"}
            # copy correct dfs (all were loaded at the beginning)
            # if career == True:
            #     dfs = dfs_career.copy()
            #     dfs_log = dfs_career_log.copy()
            # else:
            #     dfs = dfs_singleyr.copy()
            #     dfs_log = dfs_singleyr_log.copy()
            
            # remove n/a values for 'all' option
            if group1 == 'all': group1_name = 'Dataset'
            if group2 == 'all': group2_name = 'Dataset'

            data1 = get_es_aggregate(group1,group1_name,prefix)
            if data1 is not None:
                data1_log  = data1[f'{prefix}_{yr_convention_r[str(yr)]}_log']
                data1 =  data1[f'{prefix}_{yr_convention_r[str(yr)]}']
            data2 = get_es_aggregate(group2,group2_name,prefix)
            if data2 is not None:
                data2_log  = data2[f'{prefix}_{yr_convention_r[str(yr)]}_log']
                data2 =  data2[f'{prefix}_{yr_convention_r[str(yr)]}']
            
            fig_list, n1, n2 = main_group_figs(data1, data1_log, data2, data2_log, group1, group1_name, group2, group2_name, ns, logTransf, g1c = g1c, g2c = g2c)
            for i in range(6): fig_list[i].update_layout(height = 230)
            fig_list[6].update_layout(height = 250, margin = {'t':40})

            # Title
            title = 'Ranking based on composite score C and bar plots of metrics used to compute C'

            # =============== Group 1 Number of Authors LEDD Display
            if group1_name != None: group1_title = coco.convert(names = group1_name, to = 'name_short') if group1 == 'cntry' else group1_name
            nAuthors1_label = 'Number of Authors in ' + group1_title if group1_name != None else 'No group selected'
            nAuthors1 = daq.LEDDisplay(label = {"label":nAuthors1_label, "style":{"color":highlight1, "font-size":"16px"}}, value = n1, backgroundColor = darkAccent1, color = highlight1, size = 70)
            
            # =============== Group 2 Number of Authors LEDD Display
            if group2_name != None: group2_title = coco.convert(names = group2_name, to = 'name_short') if group2 == 'cntry' else group2_name
            nAuthors2_label = 'Number of Authors in ' + group2_title if group2_name != None else 'No group selected'
            nAuthors2 = daq.LEDDisplay(label = {"label":nAuthors2_label, "style":{"color":highlight2, "font-size":"16px"}}, value = n2, backgroundColor = darkAccent1, color = highlight2, size = 70)

            figures = dbc.Row([
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[0]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[1]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[2]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[3]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[4]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[5]))], width = 2)]),
            c_img = dbc.Container([dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row([dbc.Col(nAuthors1), dbc.Col(nAuthors2)]), dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row(html.Center('Composite score C formula:')), dbc.Row(html.Br()), dbc.Row(html.Img(src = 'assets/c_formula.png', style = {'width':1000}))])
            return(figures, fig_list[6], c_img)

    def main_group_figs(df1_in, df1_in_log, df2_in, df2_in_log, group1, group1_name, group2, group2_name, ns, logTransf, g1c = ['lightcoral', 'red'], g2c = ['lightblue', 'blue']):
        '''
        Output:
            7 figures (one per metric involved in calculating composite score C + composite score C)
            Number of authors in group 1
            Number of authors in group 2
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

        # # group1 df
        # if group1 == 'all':
        #     df1 = df_in.copy()
        #     df1_log = df_in_log.copy()
        # elif group1_name != None:
        #     df1 = df_in[df_in[group1] == group1_name]
        #     df1_log = df_in_log[df_in_log[group1] == group1_name]
        #     if df1.shape[0] < N_min: # if sample size too small for histogram
        #         new_y_values_1 = []
        #         new_y_values_1_log = []
        #         for m in metrics_list:
        #             new_y_values_1.append(df1[m].mean())
        #             new_y_values_1_log.append(df1_log[m].mean())
        # n1 = 0 if group1_name == None else df1.shape[0]

        # # group2 df
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
        #n2 = 0 if group2_name == None else df2.shape[0]

        if group1_name != None and df1_in != None:
            metrics_dict = get_initial_metrics_list(df1_in, group1_name, ns)
            metrics_dict_log = get_initial_metrics_list(df1_in_log, group1_name, ns)
            new_y_values_1 = list(metrics_dict.values())
            new_y_values_1.append(df1_in[cname])
            new_y_values_1_log = list(metrics_dict_log.values())
            new_y_values_1_log.append(df1_in_log[cname])
            try:
                n1 = df1_in['c'][5]
            except:
                n1= 0
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
        else:
            n2 = 0
            new_y_values_2 = [0]*7
            new_y_values_2_log = [0]*7

        # def make_bar_traces(fig, y_in, y_in_log, colors, metric, name, logTransf = False, group_num = 1):
        #     if logTransf and metric != 'c' and metric != 'c (ns)': fig.add_trace(go.Bar(name = name, x = [metric], y = [y_in], text = [y_in], textposition = 'auto',marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
        #     else: fig.add_trace(go.Bar(name = name, x = [metric], y = [y_in_log], text = [y_in], textposition = 'auto',marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
        #     fig.update_traces(texttemplate = '%{text:.5s}', textposition = 'outside')
        #     return(fig)
        
        # def make_hist_traces(fig, df, df_log, colors, metric, name, logTransf = False, group_num = 1):
        #     hovertemp = 'mean: '+str(round(df[metric].mean(),0))+'<br>'+'std: '+str(round(df[metric].std(),0))+'<br>y: %{x}<br>count: %{y}<extra></extra>'
        #     if logTransf and metric != 'c' and metric != 'c (ns)': fig.add_trace(go.Histogram(name = name,y = df_log[metric],marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
        #     else: fig.add_trace(go.Histogram(name = name,y = df[metric],marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
        #     fig.update_xaxes(row=1, col = 1, autorange="reversed") if group_num == 1 else fig.update_xaxes(row = 1, col =2, autorange=True)
        #     fig.update_traces(row=1, col = group_num, hovertemplate = hovertemp)
        #     return(fig)
        
        def make_box_traces2(fig, df, df_log, df2, df2_log, color1, color2, metric, name, logTransf = False, group_num = 1):
            if logTransf and metric != 'c' and metric != 'c (ns)':
                fig.add_trace(go.Box(y=[],name = "t1",marker_color=color2[0], boxpoints=False,),row = 1, col = group_num)
                fig.update_traces(q1= [df2_log[metric][1]], median= [df2_log[metric][2]],
                            q3= [df2_log[metric][3]], lowerfence= [df2_log[metric][0]],
                            upperfence=[df2_log[metric][4]],hoverinfo="y",selector = ({'name':'t1'}))
                fig.add_trace(go.Box(y=[],name = "t2",marker_color=color1[0], boxpoints=False,),row = 1, col = group_num)
                fig.update_traces(q1= [df_log[metric][1]], median= [df_log[metric][2]],
                            q3= [df_log[metric][3]], lowerfence= [df_log[metric][0]],
                            upperfence=[df_log[metric][4]],hoverinfo="y",selector = ({'name':'t2'}))
            else: 
                fig.add_trace(go.Box(y=[],name = "t1",marker_color=color2[0], boxpoints=False,),row = 1, col = group_num)
                fig.update_traces(q1= [df2[metric][1]], median= [df2[metric][2]],
                            q3= [df2[metric][3]], lowerfence= [df2[metric][0]],
                            upperfence=[df2[metric][4]],hoverinfo="y",selector = ({'name':'t1'}))
                fig.add_trace(go.Box(y=[],name = "t2",marker_color=color1[0], boxpoints=False,),row = 1, col = group_num)
                fig.update_traces(q1= [df[metric][1]], median= [df[metric][2]],
                            q3= [df[metric][3]], lowerfence= [df[metric][0]],
                            upperfence=[df[metric][4]],hoverinfo="y",selector = ({'name':'t2'}))

            fig.update_xaxes(row=1, col = 1, autorange="reversed") if group_num == 1 else fig.update_xaxes(row = 1, col =2, autorange=True)
            fig.update_xaxes(showgrid=False,zeroline = False)
            fig.update_yaxes(showgrid=False,zeroline = False)
            fig.update_layout(boxmode='group', boxgroupgap=0.1, boxgap = 0, hovermode='x unified')
            return(fig)
        
        # def make_violin_traces(fig, df, df_log, df2, df2_log, color1, color2, metric, name, logTransf = False, group_num = 1):
        #     if logTransf:
        #         fig = get_violin_compare(fig,df_log[metric],df2_log[metric],color1,color2,name, group_num)
        #     else:
        #         fig = get_violin_compare(fig,df[metric],df2[metric],color1,color2,name, group_num)
        #     fig.update_xaxes(row=1, col = 1, autorange="reversed") if group_num == 1 else fig.update_xaxes(row = 1, col =2, autorange=True)
        #     return fig
        # metric titles
        subplot_titles = ['Number of citations<br>(NC)', 'H-index<br>(H)', 'Hm-index<br>(Hm)', 'Number of citations to<br>single authored papers<br>(NCS)', 
            'Number of citations to<br>single and first<br>authored papers<br>(NCSF)', 'Number of citations to<br>single, first and<br>last authored papers<br>(NCSFL)', 'Composite score (C)']
        
        # get figs!
        fig_list = []
        for i, m in enumerate(metrics_list):
            fig = make_subplots(rows = 1, cols = 1)
            if group1_name != None: group1_legend = coco.convert(names=group1_name, to='name_short') if group1 == 'cntry' else group1_name
            if group2_name != None: group2_legend = coco.convert(names=group2_name, to='name_short') if group2 == 'cntry' else group2_name

            logTransf_val = False if i == 6 else logTransf # do not log-transform C-score

            if group1_name != None and group2_name != None:
                fig = make_box_traces2(fig, df1_in, df1_in_log, df2_in, df2_in_log, g1c, g2c, m, group1_legend, logTransf = logTransf_val, group_num = 1)
            
            # if group1_name != None and group2_name == None: # FIGURE: G2 None
            #     fig = make_subplots(rows = 1, cols = 1)
            #     #if df1.shape[0] < N_min: fig = make_bar_traces(fig, y_in = new_y_values_1[i], y_in_log = new_y_values_1_log[i], colors = g1c, metric = m, name = group1_legend, logTransf = logTransf_val, group_num = 1)
            #     fig = make_hist_traces(fig, df1, df1_log, colors = g1c, metric = m, name = group1_legend, logTransf = logTransf_val, group_num = 1) 
            # elif group2_name != None and group1_name == None: # FIGURE: G1 None
            #     fig = make_subplots(rows = 1, cols = 1)
            #     #if df2.shape[0] < N_min: fig = make_bar_traces(fig, y_in = new_y_values_2[i], y_in_log = new_y_values_2_log[i], colors = g2c, metric = m, name = group2_legend, logTransf = logTransf_val, group_num = 1)
            #     fig = make_hist_traces(fig, df2, df2_log, colors = g2c, metric = m, name = group2_legend, logTransf = logTransf_val, group_num = 1)
            # elif df1.shape[0] < N_min:
            #     if df2.shape[0] < N_min: # FIGURE: G1 Bar Plot, G2 Bar Plot
            #         fig = make_subplots(rows = 1, cols = 2,column_widths=[0.5, 0.5],shared_yaxes=True,horizontal_spacing = 0)
            #         fig = make_bar_traces(fig, y_in = new_y_values_1[i], y_in_log = new_y_values_1_log[i], colors = g1c, metric = m, name = group1_legend, logTransf = logTransf_val, group_num = 1) 
            #         fig = make_bar_traces(fig, y_in = new_y_values_2[i], y_in_log = new_y_values_2_log[i], colors = g2c, metric = m, name = group2_legend, logTransf = logTransf_val, group_num = 2)
            #     else: # FIGURE: G1 Scatter Plot, G2 Histogram
            #         fig = make_subplots(rows = 1, cols = 1)
            #         fig = make_hist_traces(fig, df2, df2_log, colors = g2c, metric = m, name = group2_legend, logTransf = logTransf_val)
            #         if logTransf and m != 'c' and m != 'c (ns)': fig.add_hline(new_y_values_1_log[i], line_color = g1c[0], line_width = 4, annotation_text= 'mean: ' + str(round(new_y_values_1[i],2)), annotation_font_color=g1c[0], annotation_position="top left")
            #         else: fig.add_hline(new_y_values_1[i], line_color = g1c[0], line_width = 4, annotation_text= 'mean: ' + str(round(new_y_values_1[i],2)), annotation_font_color=g1c[0], annotation_position="top left")
            # elif df2.shape[0] < N_min: # FIGURE: G1 Histogram, G2Scatter Plot
            #     fig = make_subplots(rows = 1, cols = 1)
            #     fig = make_hist_traces(fig, df1, df1_log, colors = g1c, metric = m, name = group1_legend, logTransf = logTransf_val, group_num = 1) 
            #     if logTransf and m != 'c' and m != 'c (ns)': fig.add_hline(new_y_values_2_log[i], line_color = g2c[0], line_width = 4, annotation_text= 'mean: ' + str(round(new_y_values_2[i],2)), annotation_font_color=g2c[0], annotation_position="top left")
            #     else: fig.add_hline(new_y_values_2[i], line_color = g2c[0], line_width = 4, annotation_text= 'mean: ' + str(round(new_y_values_2[i],2)), annotation_font_color=g2c[0], annotation_position="top left")
            # else: # FIGURE: G1 Histogram, G2 Histogram
            #     fig = make_subplots(rows = 1, cols = 2,column_widths=[0.5, 0.5],shared_yaxes=True,horizontal_spacing = 0)
            #     fig = make_hist_traces(fig, df1, df1_log, colors = g1c, metric = m, name = group1_legend, logTransf = logTransf_val, group_num = 1) 
            #     fig = make_hist_traces(fig, df2, df2_log, colors = g2c, metric = m, name = group2_legend, logTransf = logTransf_val, group_num = 2) 
            fig.update_layout(height = 500, title_x = 0.5, title = {'text':subplot_titles[i], 'font':{'size':14}}, font = {'size':12, 'color':lightAccent1}, showlegend = False, 
                plot_bgcolor = bgc, paper_bgcolor = bgc, margin = {'l':10, 'r':5, 'b':0})
            # if logTransf and m != 'c' and m != 'c (ns)':
            #     if i == 6: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, range = [0, df_in[m].max()]) # do not log-transform C score y-axis
            #     else: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2,
            #         tickvals = [k*(df_in_log[m].max()/6) for k in range(0,6)],
            #         ticktext = [int(np.exp(k*(df_in_log[m].max()/6)*(np.log(df_in[m].max() + 1)))) for k in range(0,6)],
            #         range = [0, df_in_log[m].max()])
            # else: fig.update_yaxes(showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, range = [0, df_in[m].max()])
            fig.update_xaxes(automargin = True, showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, tickmode = "array", tickvals = [])
            fig_list.append(fig)
        return(fig_list, n1, n2)

    row3 = html.Div([
        dbc.Row(html.Br()),
        dbc.Row([dbc.Col(logTransf, width = {'offset':4, 'size':2}), dbc.Col(selfC, width = {'size':2})]), 
        dbc.Row(html.Br()), metricsFig_c, dbc.Row(html.Br()), 
        dbc.Row(dbc.Col(dbc.Container(id = '2group_figs' + SUFFIX), width = {'offset':1,'size':10})), dbc.Row(html.Br()), 
    ])

    # ========================================================================================== 
    # ========================================================================================== 
    # Layout
    # ========================================================================================== 
    # ========================================================================================== 
    return(html.Div([
        dbc.Container(fluid = True, children = [
            html.Br(),
            row1, 
            html.Hr(),
            dls.GridFade(html.Div([ 
            row2,
            html.Hr(), 
            row3,
            html.Br()]),color="#ECAB4C"),
        ], style = {'backgroundColor':darkAccent1}), 
    ]))