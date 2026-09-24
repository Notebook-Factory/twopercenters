# ==========================================================================================
# ==========================================================================================
# IMPORT LIBRARIES
# ==========================================================================================
# ==========================================================================================

# =============== misc libs & modules
import numpy as np

# =============== Plotly libs & modules
import plotly.graph_objects as go
import country_converter as coco

# =============== Plotly Dash libraries
from dash import html, dcc
from citations_lib.callbacks import callback
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq
import dash_loading_spinners as dls

# =============== Custom lib
from citations_lib.utils import (
    es_result_pick, get_es_aggregate, get_es_results, load_dropdown_opts,
    yr_convention_map)
from citations_lib.callback_templates import (
    generate_es_dropdown_callback, generate_update_cards_callback,
    generate_update_carsing_callback, generate_update_years_callback)
from citations_lib.create_fig_helper_functions import get_initial_metrics_list
from plotly.subplots import make_subplots
from citations_lib.controls import kind_toggle

def author_vs_group_layout(default_author=None):
    """The author side is seeded from the dashboard's current author."""
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

    SUFFIX = '_author_vs_group'

    # ==========================================================================================
    # ==========================================================================================
    # Dataset and year for the author
    # ==========================================================================================
    # ==========================================================================================

    # =============== Career vs Singleyr
    careerORSingleA1 = kind_toggle("careerORSingleYrA1" + SUFFIX)

    # =============== Year
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
    ], className = "radio-group year-picker")

    # year -> radio index, the inverse of yr_convention_map. Derived from the
    # editions loaded in Postgres, not hardcoded: these used to stop at 2021,
    # so 2022, 2023 and 2024 raised KeyError.
    single_yr_convention = {year: int(index) for index, year
                            in yr_convention_map(False).items()}
    career_yr_convention = {year: int(index) for index, year
                            in yr_convention_map(True).items()}

    # ==========================================================================================
    # ========================================================================================== 
    # Row 2 Select groups
    # ========================================================================================== 
    # ========================================================================================== 

    # =============== Group 1 (author) Dropdown

    group1List = dcc.Dropdown(options = [], placeholder = 'Search researchers', multi = False, id = "group1ListDropdown" + SUFFIX, 
    value = default_author or 'Ioannidis, John P.A.', searchable = True)
    generate_es_dropdown_callback("group1ListDropdown" + SUFFIX)
    generate_update_carsing_callback('group1ListDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX)
    generate_update_years_callback('careerORSingleYrA1' + SUFFIX, 'selectYrRadioA1' + SUFFIX, 'group1ListDropdown' + SUFFIX)
    output_ids = ['InfoAuthor1' + SUFFIX, 'FieldAuthor1' + SUFFIX, 'CountryAuthor1' + SUFFIX, 'InstitutionAuthor1' + SUFFIX]
    generate_update_cards_callback('selectYrRadioA1' + SUFFIX, output_ids, 'group1ListDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX,darkAccent1, highlight1)

    # =============== Group 2 Dropdowns
    group2List = dcc.Dropdown(id = "group2ListDropdown" + SUFFIX, 
        placeholder = 'Choose a group type', multi = False, searchable = True, value = 'sm-field', style = {'background-color':'var(--ev-surface)'},
        options = [{'label':'Country', 'value': 'cntry'}, {'label':'Field', 'value': 'sm-field'}, {'label':'Institution', 'value': 'inst_name'}])
    group2ListOptions = dcc.Dropdown(id = "group2ListOptionsDropdown" + SUFFIX,value = 'Clinical Medicine', searchable = True)
    # =============== Group 2 Callbacks
    @callback(
        Output('group2ListOptionsDropdown' + SUFFIX, 'options'), Output('group2ListOptionsDropdown'+ SUFFIX, 'placeholder'), 
        Input('careerORSingleYrA1'+ SUFFIX, 'value'), Input('selectYrRadioA1'+ SUFFIX, 'value'), 
        Input('group2ListDropdown'+ SUFFIX, 'value'), Input('group2ListOptionsDropdown'+ SUFFIX, 'search_value'))
    def update_group_2_dropdown_options(career, yr, value, search_value):
        if career == None or yr == None or not value: raise PreventUpdate
        else:
            # dropdown_opts is keyed by radio index, not by year
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
                return [{'label':name, 'value':value} for name, value in zip(optns_names, optns)], 'Select country'
            else: return [{'label':name, 'value':name} for name in optns], 'Select field'
    
    @callback(
        Output('Group2Title'+ SUFFIX, 'children'), Output('Group2Info'+ SUFFIX, 'children'), 
        Input('careerORSingleYrA1' + SUFFIX, 'value'), Input('selectYrRadioA1' + SUFFIX, 'value'), 
        Input('group2ListDropdown'+ SUFFIX, 'value'), Input('group2ListOptionsDropdown'+ SUFFIX, 'value'))
    def update_group_2_dropdown_values(career, yr, group, group_name):
        if career == None or yr == None or group == None or group_name == None: raise PreventUpdate
        else:
            prefix1 = 'career' if career else 'singleyr'
            data = get_es_aggregate(group,group_name,prefix1)
            # get_es_aggregate returns {} for a name it has no group for, such
            # as "Clinical Medicine" still selected just after the group type
            # was switched from Field to Country. That falls through to the
            # same "choose one" card as any other name that cannot be shown.
            key = f'{prefix1}_{yr}'
            self_cit = np.round(data[key]['self%'][2]*100,2) if key in data else None

            if group == 'cntry': 
                title = 'Country'
                card1 = dbc.Card(html.Center('Group: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                try:
                    if self_cit is None: raise KeyError(key)
                    card2 = dbc.Card(html.Center(coco.convert(names = group_name, to = 'name_short') + ' (' + str(self_cit) + '% median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
                except:
                    card2 = dbc.Card(html.Center('Select a country to start.'), style = {'color':darkAccent1, 'font-size':14}, color = highlight2)
            else:
                title = 'Field' if group == 'sm-field' else 'Institution'
                card1 = dbc.Card(html.Center('Group: ' + title, style = {'color':darkAccent1, 'font-size':18}), color = highlight2)
                try:
                    if self_cit is None: raise KeyError(key)
                    card2 = dbc.Card(html.Center(group_name + ' (' + str(self_cit) + '% median self-citation)', style = {'color':darkAccent1, 'font-size':14}), color = highlight2)
                except:
                    card2 = dbc.Card(html.Center('Choose a group.'), style = {'color':darkAccent1, 'font-size':14}, color = highlight2)
            return(card1, card2)

    row2 = dbc.Container([
        dbc.Row([
            dbc.Col([html.Center(group1List), html.Div([html.Div(careerORSingleA1, className="ev-picker-left"), html.Span(className="ev-picker-sep"), html.Div(selectYrA1, className="ev-picker-right")], className="ev-picker ev-picker-inline") ], width = {'size':6}), 
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
    # =============== C score figure
    metricsFig_c = dbc.Row([dbc.Col([html.Center(dcc.Graph(id = 'metricsFigGraphAuthor_c' + SUFFIX, figure = empty_fig, config = {'displayModeBar': False}))], width = {'offset':1, 'size':2}), dbc.Col(id = 'c_score_formula' + SUFFIX, width = 7)])
    # =============== Figure callbacks
    @callback(
        Output('2group_figs' + SUFFIX, 'children'), 
        Output('metricsFigGraphAuthor_c' + SUFFIX, 'figure'), 
        Output('c_score_formula' + SUFFIX, 'children'),
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
        group2: country, institution, field
        '''
        if career1 == None or yr1 == None: raise PreventUpdate
        # One value per output, in the order the outputs are declared.
        elif group1_name == None and group2_name == None: return ("No dataset selected", empty_fig, '')
        else:

            prefix1 = 'career' if career1 else 'singleyr'
            # exact=True: the author name comes from the dropdown.
            results = get_es_results(group1_name, prefix1, 'authfull', exact=True)
            data1 = {}
            data1_log = {}
            if results is not None:
                data1 = es_result_pick(results, 'data', None)
                data1_log  = data1[f'{prefix1}_{yr1}_log']
                data1 =  data1[f'{prefix1}_{yr1}']

            # get_es_aggregate returns {}, never None, for a name it has no
            # group for, such as "Clinical Medicine" still selected just after
            # the group type was switched from Field to Country. Such a name
            # is drawn as no group at all, rather than read and failed on.
            data2 = get_es_aggregate(group2,group2_name,prefix1) if group2_name != None else {}
            if f'{prefix1}_{yr1}' in data2:
                data2_log  = data2[f'{prefix1}_{yr1}_log']
                data2 =  data2[f'{prefix1}_{yr1}']
            else:
                data2, data2_log, group2_name = None, None, None

            fig_list, n1, n2 = main_author_group_figs(data1, data1_log, data2, data2_log, group1_name, group2, group2_name, ns, logTransf, g1c = g1c, g2c = g2c)
            for i in range(6): fig_list[i].update_layout(height = 230)
            fig_list[6].update_layout(height = 250, margin = {'t':40})

            # =============== Group 1 Number of Authors LEDD Display
            authorRank_label = 'Global rank of ' + group1_name if group1_name != None else 'No author selected'
            authorRank = daq.LEDDisplay(label = {"label":authorRank_label, "style":{"color":highlight1, "font-size":"16px"}}, value = n1, backgroundColor = darkAccent1, color = highlight1, size = 70)
            
            # =============== Group 2 Number of Authors LEDD Display
            if group2_name != None: group2_title = coco.convert(names = group2_name, to = 'name_short') if group2 == 'cntry' else group2_name
            nAuthors2_label = 'Researchers in ' + group2_title if group2_name != None else 'No group selected'
            nAuthors2 = daq.LEDDisplay(label = {"label":nAuthors2_label, "style":{"color":highlight2, "font-size":"16px"}}, value = n2, backgroundColor = darkAccent1, color = highlight2, size = 70)

            figures = dbc.Row([
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[0]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[1]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[2]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[3]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[4]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[5]))], width = 2)]),
            c_img = dbc.Container([dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row([dbc.Col(authorRank), dbc.Col(nAuthors2)]), dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row(html.Center('Composite score (C)')), dbc.Row(html.Br()), dbc.Row(dcc.Markdown(
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

    def main_author_group_figs(df1_in, df1_in_log, df2_in, df2_in_log, group1_name, group2, group2_name, ns, logTransf, g1c = ['lightcoral', 'red'], g2c = ['lightblue', 'blue']):
        '''
        Output:
            7 figures (one per metric involved in calculating composite score C + composite score C)
            Rank of author
            Number of authors in group
        '''
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

        def make_box_traces(fig, df, df_log, colors, metric, name, logTransf = False, group_num = 1):
            if logTransf and metric != 'c' and metric != 'c (ns)':
                fig.add_trace(go.Box(name=name,marker_color=colors[0],hovertext=['Min', 'Median', 'Max']),row = 1, col = group_num)
                fig.update_traces(name=name,q1= [df_log[metric][1]], median= [df_log[metric][2]],
                            q3= [df_log[metric][3]], lowerfence= [df_log[metric][0]],
                            upperfence=[df_log[metric][4]], hoverinfo="y")
            else: 
                fig.add_trace(go.Box(name=name,marker_color=colors[0]),row = 1, col = group_num)
                fig.update_traces(q1= [df[metric][1]], median= [df[metric][2]],
                            q3= [df[metric][3]], lowerfence= [df[metric][0]],
                            upperfence=[df[metric][4]],hoverinfo="y")
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
                fig = make_box_traces(fig, df2_in, df2_in_log, colors = g2c, metric = m, name = group2_legend, logTransf = logTransf_val, group_num = 1)
            else: 
                fig.add_trace(go.Bar(x = [m], y = [0], text = [0], marker_color = g1c[0], marker_line_width = 0), row = 1, col = 1)
            if group1_name != None: 
                if logTransf and m != 'c' and m != 'c (ns)': fig.add_hline(new_y_values_1_log[i], line_color = g1c[0], line_width = 4, annotation_text= 'Author: ' + str(round(new_y_values_1[i],2)), annotation_font_color=g1c[0], annotation_position="top left")
                else: fig.add_hline(new_y_values_1[i], line_color = g1c[0], line_width = 4, annotation_text= 'Author: ' + str(round(new_y_values_1[i],2)), annotation_font_color=g1c[0], annotation_position="top left")
            fig.update_layout(height = 500, title_x = 0.5, title = {'text':subplot_titles[i], 'font':{'size':14}}, font = {'size':12, 'color':lightAccent1}, showlegend = False, 
                plot_bgcolor = bgc, paper_bgcolor = bgc, margin = {'l':10, 'r':5, 'b':0})
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
        ], className = 'ev-page')]))
