# ========================================================================================== 
# ========================================================================================== 
# IMPORT LIBRARIES
# ========================================================================================== 
# ========================================================================================== 

# =============== Plotly libs & modules
import plotly.graph_objects as go
import country_converter as coco

# =============== Plotly Dash libraries
from dash import html, dcc
from citations_lib.callbacks import callback
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq

# =============== Custom lib
import numpy as np
from citations_lib.utils import (
    get_es_aggregate, load_dropdown_opts, update_yr_options,
    yr_convention_map)
from citations_lib.create_fig_helper_functions import get_initial_metrics_list
from plotly.subplots import make_subplots
import dash_loading_spinners as dls
from citations_lib.controls import kind_toggle

def group_vs_group_layout():
    # ========================================================================================== 
    # ========================================================================================== 
    # Data Preparation
    # ========================================================================================== 
    # ==========================================================================================

    # Was nine aggregate/info_*.pkl files, one per edition, which only covered
    # radio indices career 0-4 and singleyr 0-3; selecting 2022 or later
    # raised KeyError('career 5') when filling a group dropdown. Same dict,
    # computed from every edition actually loaded.
    dropdown_opts = load_dropdown_opts()

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

    g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
    g2c = [highlight2, darkAccent3] # bar plot bar 3
    # Transparent, not a colour: the page's own background shows through,
    # so a chart follows the light/dark switch without being redrawn.
    bgc = 'rgba(0,0,0,0)' # chart background: inherit the page
    SUFFIX = '_group_vs_group'

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 1: select dataset!
    # ========================================================================================== 
    # ==========================================================================================

    # =============== Career vs Singleyr
    careerORSingleYr = kind_toggle("careerORSingleYrRadio" + SUFFIX)
    # =============== Year
    selectYr = html.Div(
        [dbc.RadioItems(
            id = "selectYrRadio" + SUFFIX, className = "btn-group", inputClassName = "btn-check", 
            labelClassName = "btn btn-outline-primary", labelCheckedClassName = "active", style = {'size':'sm'}, 
            options = update_yr_options(career = True), value = 3)
    ], className = "radio-group year-picker")
    @callback(
        Output('selectYrRadio' + SUFFIX, 'options'), 
        Output('selectYrRadio' + SUFFIX, 'value'), 
        Input('careerORSingleYrRadio' + SUFFIX, 'value'),
        State('selectYrRadio' + SUFFIX, 'value'),
        State('selectYrRadio' + SUFFIX, 'options'))
    def update_yr_opts(career, yr, old_options):
        # The value is an index into the year list, and the same index is a
        # different year in each dataset: 2 is 2019 in career and 2020 in
        # single-year, and career's 7 (2024) does not exist in single-year at
        # all. So the year is read off the label of the option that was
        # selected, and the same year is selected in the new list; if the new
        # dataset has no such year, the latest one it has is selected instead.
        # On page load the options are already this dataset's, so the value
        # comes back unchanged.
        options = update_yr_options(career)
        def year_of(option): return str(option['label']).split(' ')[-1] # 'TO 2017' -> '2017'
        old_year = next((year_of(o) for o in (old_options or []) if o.get('value') == yr), None)
        selectable = [o for o in options if 'value' in o] # not the disabled 2018 placeholder
        same_year = [o['value'] for o in selectable if year_of(o) == old_year]
        return(options, same_year[0] if same_year else selectable[-1]['value'])

    # The "Select dataset" card that used to sit here was a large bordered box
    # whose whole content was the words "Select dataset", restating what the
    # control beside it already said. The two controls carry their own captions
    # now, in the same labelled-toolbar shape the home page uses.
    row1 = html.Div(
        [
            html.Div(
                [
                    html.Div(careerORSingleYr, className="ev-picker-left"),
                    html.Span(className="ev-picker-sep"),
                    html.Div(selectYr, className="ev-picker-right"),
                ],
                className="ev-picker",
            ),
        ],
        className="ev-toolbar ev-panel-toolbar",
    )

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 2 Select groups
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Group 1 Dropdowns
    # There used to be an "All" group type as well. Nothing holds an
    # aggregate over every researcher (group_metrics has only countries and
    # fields, and institutions are computed live), so get_es_aggregate('all')
    # returned {} and every callback below raised KeyError on it.
    group1List = dcc.Dropdown(id = "group1ListDropdown" + SUFFIX, 
        placeholder = 'Choose a group type', multi = False, value = 'sm-field', searchable = True,
        options = [{'label':'Country', 'value': 'cntry'}, {'label':'Field', 'value': 'sm-field'}, {'label':'Institution', 'value': 'inst_name'}])
    group1ListOptions = dcc.Dropdown(id = "group1ListOptionsDropdown" + SUFFIX,value = 'Clinical Medicine', searchable = True)
    # =============== Group 1 Callbacks
    @callback(
        Output('group1ListOptionsDropdown' + SUFFIX, 'options'), Output('group1ListOptionsDropdown'+ SUFFIX, 'placeholder'), 
        Input('careerORSingleYrRadio'+ SUFFIX, 'value'), Input('selectYrRadio'+ SUFFIX, 'value'), 
        Input('group1ListDropdown'+ SUFFIX, 'value'), Input('group1ListOptionsDropdown'+ SUFFIX, 'search_value'))
    def update_group_1_dropdown_options(career, yr, value, search_value):
        if career == None or yr == None or not value: raise PreventUpdate
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
                return [{'label':name, 'value':value} for name, value in zip(optns_names, optns)], 'Select country'
            else: return [{'label':name, 'value':name} for name in optns], 'Select field'
    @callback(
        Output('Group1Title'+ SUFFIX, 'children'), Output('Group1Info'+ SUFFIX, 'children'), 
        Input('careerORSingleYrRadio' + SUFFIX, 'value'), Input('selectYrRadio' + SUFFIX, 'value'), 
        Input('group1ListDropdown'+ SUFFIX, 'value'), Input('group1ListOptionsDropdown'+ SUFFIX, 'value'))
    def update_group_1_dropdown_values(career, yr, group, group_name):
        if career == None or yr == None or group == None or group_name == None: raise PreventUpdate
        else:
            # Derived from the editions loaded in Postgres, not hardcoded:
            # this map used to stop at index 4 / 2021, so selecting 2022,
            # 2023 or 2024 raised KeyError.
            yr_convention_r = yr_convention_map(career)
           
            prefix = 'career' if career else 'singleyr'
            data = get_es_aggregate(group,group_name,prefix)
            # get_es_aggregate returns {} for a name it has no group for, such
            # as "Clinical Medicine" still selected just after the group type
            # was switched from Field to Country. That name gets the same
            # "choose one" card the author-vs-group tab shows.
            key = f'{prefix}_{yr_convention_r[str(yr)]}'
            self_cit = np.round(data[key]['self%'][2]*100,2) if key in data else None

            if group == 'cntry': 
                title = 'Country'
                card1 = dbc.Card(html.Center('Group 1: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
                if self_cit is None: card2 = dbc.Card(html.Center('Select a country to start.'), style = {'color':darkAccent1, 'font-size':14}, color = highlight1)
                else: card2 = dbc.Card(html.Center(coco.convert(names = group_name, to = 'name_short') + ' (' + str(self_cit) + '% median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight1)
            else:
                title = 'Field' if group == 'sm-field' else 'Institution'
                card1 = dbc.Card(html.Center('Group 1: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight1)
                if self_cit is None: card2 = dbc.Card(html.Center('Choose a group.'), style = {'color':darkAccent1, 'font-size':14}, color = highlight1)
                else: card2 = dbc.Card(html.Center(group_name + ' (' + str(self_cit) + '% median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight1)
            return(card1, card2)

    # =============== Group 2 Dropdowns
    group2List = dcc.Dropdown(id = "group2ListDropdown" + SUFFIX, 
        placeholder = 'Choose a group type', multi = False, value = 'cntry', searchable = True,
        options = [{'label':'Country', 'value': 'cntry'}, {'label':'Field', 'value': 'sm-field'}, {'label':'Institution', 'value': 'inst_name'}])
    group2ListOptions = dcc.Dropdown(id = "group2ListOptionsDropdown" + SUFFIX,value = 'usa', searchable = True)
    # =============== Group 2 Callbacks
    @callback(
        Output('group2ListOptionsDropdown' + SUFFIX, 'options'), Output('group2ListOptionsDropdown'+ SUFFIX, 'placeholder'), 
        Input('careerORSingleYrRadio'+ SUFFIX, 'value'), Input('selectYrRadio'+ SUFFIX, 'value'), 
        Input('group2ListDropdown'+ SUFFIX, 'value'), Input('group2ListOptionsDropdown'+ SUFFIX, 'search_value'))
    def update_group_2_dropdown_options(career, yr, value, search_value):
        if career == None or yr == None or not value: raise PreventUpdate
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
                return [{'label':name, 'value':value} for name, value in zip(optns_names, optns)], 'Select country'
            else: return [{'label':name, 'value':name} for name in optns], 'Select field'
    @callback(
        Output('Group2Title'+ SUFFIX, 'children'), Output('Group2Info'+ SUFFIX, 'children'), 
        Input('careerORSingleYrRadio' + SUFFIX, 'value'), Input('selectYrRadio' + SUFFIX, 'value'), 
        Input('group2ListDropdown'+ SUFFIX, 'value'), Input('group2ListOptionsDropdown'+ SUFFIX, 'value'))
    def update_group_2_dropdown_values(career, yr, group, group_name):
        if career == None or yr == None or group == None or group_name == None: raise PreventUpdate
        else:
            # Derived from the editions loaded in Postgres, not hardcoded:
            # this map used to stop at index 4 / 2021, so selecting 2022,
            # 2023 or 2024 raised KeyError.
            yr_convention_r = yr_convention_map(career)
           
            prefix = 'career' if career else 'singleyr'
            data = get_es_aggregate(group,group_name,prefix)
            # get_es_aggregate returns {} for a name it has no group for, such
            # as "Clinical Medicine" still selected just after the group type
            # was switched from Field to Country. That name gets the same
            # "choose one" card the author-vs-group tab shows.
            key = f'{prefix}_{yr_convention_r[str(yr)]}'
            self_cit = np.round(data[key]['self%'][2]*100,2) if key in data else None

            if group == 'cntry': 
                title = 'Country'
                card1 = dbc.Card(html.Center('Group 2: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                if self_cit is None: card2 = dbc.Card(html.Center('Select a country to start.'), style = {'color':darkAccent1, 'font-size':14}, color = highlight2)
                else: card2 = dbc.Card(html.Center(coco.convert(names = group_name, to = 'name_short') + ' (' + str(self_cit) + '% median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
            else:
                title = 'Field' if group == 'sm-field' else 'Institution'
                card1 = dbc.Card(html.Center('Group 2: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                if self_cit is None: card2 = dbc.Card(html.Center('Choose a group.'), style = {'color':darkAccent1, 'font-size':14}, color = highlight2)
                else: card2 = dbc.Card(html.Center(group_name + ' (' + str(self_cit) + '% median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
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
    logTransf = daq.BooleanSwitch(label = 'Log transformed', labelPosition = 'bottom', id = 'logTransfToggleMain' + SUFFIX,
                                  className = 'ev-switch ev-switch-log')
    # =============== Toggle: % self-citations
    selfC = daq.BooleanSwitch(label = 'Exclude self-citations', labelPosition = 'bottom', id = 'selfCToggle' + SUFFIX,
                              className = 'ev-switch ev-switch-selfcite')
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
        group1: country, institution, field
        group2: country, institution, field
        '''
        if career == None or yr == None: raise PreventUpdate
        # One value per output, in the order the outputs are declared.
        elif group1_name == None and group2_name == None: return ("No dataset selected", empty_fig, '')
        else:
            
            prefix = 'career' if career else 'singleyr'
            # Derived from the editions loaded in Postgres, not hardcoded:
            # this map used to stop at index 4 / 2021, so selecting 2022,
            # 2023 or 2024 raised KeyError.
            yr_convention_r = yr_convention_map(career)

            # get_es_aggregate returns {}, never None, for a name it has no
            # group for, such as "Clinical Medicine" still selected just after
            # the group type was switched from Field to Country. Such a name
            # is drawn as no group at all, rather than read and failed on.
            key = f'{prefix}_{yr_convention_r[str(yr)]}'
            data1 = get_es_aggregate(group1,group1_name,prefix) if group1_name != None else {}
            if key in data1:
                data1_log  = data1[f'{key}_log']
                data1 =  data1[key]
            else:
                data1, data1_log, group1_name = None, None, None
            data2 = get_es_aggregate(group2,group2_name,prefix) if group2_name != None else {}
            if key in data2:
                data2_log  = data2[f'{key}_log']
                data2 =  data2[key]
            else:
                data2, data2_log, group2_name = None, None, None
            
            fig_list, n1, n2 = main_group_figs(data1, data1_log, data2, data2_log, group1, group1_name, group2, group2_name, ns, logTransf, g1c = g1c, g2c = g2c)
            for i in range(6): fig_list[i].update_layout(height = 230)
            fig_list[6].update_layout(height = 250, margin = {'t':40})

            # =============== Group 1 Number of Authors LEDD Display
            if group1_name != None: group1_title = coco.convert(names = group1_name, to = 'name_short') if group1 == 'cntry' else group1_name
            nAuthors1_label = 'Researchers in ' + group1_title if group1_name != None else 'No group selected'
            nAuthors1 = daq.LEDDisplay(label = {"label":nAuthors1_label, "style":{"color":highlight1, "font-size":"16px"}}, value = n1, backgroundColor = darkAccent1, color = highlight1, size = 70)
            
            # =============== Group 2 Number of Authors LEDD Display
            if group2_name != None: group2_title = coco.convert(names = group2_name, to = 'name_short') if group2 == 'cntry' else group2_name
            nAuthors2_label = 'Researchers in ' + group2_title if group2_name != None else 'No group selected'
            nAuthors2 = daq.LEDDisplay(label = {"label":nAuthors2_label, "style":{"color":highlight2, "font-size":"16px"}}, value = n2, backgroundColor = darkAccent1, color = highlight2, size = 70)

            figures = dbc.Row([
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[0]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[1]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[2]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[3]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[4]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[5]))], width = 2)]),
            c_img = dbc.Container([dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row([dbc.Col(nAuthors1), dbc.Col(nAuthors2)]), dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row(html.Center('Composite score (C)')), dbc.Row(html.Br()), dbc.Row(dcc.Markdown(
                r'''
$$
C_i \;=\; \frac{\log(NC_i)}{\mathrm{maxlog}(NC)}
\;+\; \frac{\log(H_i)}{\mathrm{maxlog}(H)}
\;+\; \frac{\log(Hm_i)}{\mathrm{maxlog}(Hm)}
\;+\; \frac{\log(NCS_i)}{\mathrm{maxlog}(NCS)}
\;+\; \frac{\log(NCSF_i)}{\mathrm{maxlog}(NCSF)}
\;+\; \frac{\log(NCSFL_i)}{\mathrm{maxlog}(NCSFL)}
$$
''', mathjax=True, className='ev-formula'))])
            return(figures, fig_list[6], c_img)

    def main_group_figs(df1_in, df1_in_log, df2_in, df2_in_log, group1, group1_name, group2, group2_name, ns, logTransf, g1c = ['lightcoral', 'red'], g2c = ['lightblue', 'blue']):
        '''
        Output:
            7 figures (one per metric involved in calculating composite score C + composite score C)
            Number of authors in group 1
            Number of authors in group 2
        '''
        # list of metrics
        metrics_list = ['nc (ns)','h (ns)','hm (ns)',  'ncs (ns)', 'ncsf (ns)','ncsfl (ns)','c (ns)'] if ns else ['nc', 'h', 'hm',  'ncs', 'ncsf','ncsfl','c']
        cname = 'c (ns)' if ns else 'c'

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
        
        # metric titles
        subplot_titles = ['Number of citations<br>(NC)', 'H-index<br>(H)', 'Hm-index<br>(Hm)', 'Number of citations to<br>single authored papers<br>(NCS)', 
            'Number of citations to<br>single and first<br>authored papers<br>(NCSF)', 'Number of citations to<br>single, first and<br>last authored papers<br>(NCSFL)', 'Composite score (C)']
        
        # get figs!
        fig_list = []
        for i, m in enumerate(metrics_list):
            fig = make_subplots(rows = 1, cols = 1)
            if group1_name != None: group1_legend = coco.convert(names=group1_name, to='name_short') if group1 == 'cntry' else group1_name

            logTransf_val = False if i == 6 else logTransf # do not log-transform C-score

            if group1_name != None and group2_name != None:
                fig = make_box_traces2(fig, df1_in, df1_in_log, df2_in, df2_in_log, g1c, g2c, m, group1_legend, logTransf = logTransf_val, group_num = 1)

            fig.update_layout(height = 500, title_x = 0.5, title = {'text':subplot_titles[i], 'font':{'size':14}}, font = {'size':12, 'color':lightAccent1}, showlegend = False,
                plot_bgcolor = bgc, paper_bgcolor = bgc, margin = {'l':10, 'r':5, 'b':0})
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
        ], className = 'ev-page'), 
    ]))
