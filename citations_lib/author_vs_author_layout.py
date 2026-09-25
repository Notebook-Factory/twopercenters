# ==========================================================================================
# ==========================================================================================
# IMPORT LIBRARIES
# ==========================================================================================
# ==========================================================================================

# =============== Plotly libs & modules
import plotly.graph_objects as go

# =============== Plotly Dash libraries
from dash import html, dcc
from citations_lib.callbacks import callback
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq

# =============== Custom lib
from citations_lib.utils import es_result_pick, get_es_results
from citations_lib.callback_templates import (
    generate_es_dropdown_callback, generate_update_cards_callback,
    generate_update_carsing_callback, generate_update_years_callback)
from citations_lib.create_fig_helper_functions import get_initial_metrics_list
from plotly.subplots import make_subplots
import dash_loading_spinners as dls
from citations_lib.controls import kind_toggle


def author_vs_author_layout(default_author=None):
    """Author 1 is seeded from the dashboard's current author when there is
    one, so picking someone in any panel carries across to this one."""

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
    SUFFIX = '_author_vs_author'

    # ==========================================================================================
    # ==========================================================================================
    # Select authors, and a dataset and year for each
    # ==========================================================================================
    # ==========================================================================================

    # =============== Career vs Singleyr
    careerORSingleA1 = kind_toggle("careerORSingleYrA1" + SUFFIX)
    careerORSingleA2 = kind_toggle("careerORSingleYrA2" + SUFFIX)

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
    ], className = "radio-group year-picker")

    # =============== Author 1 Callbacks
    author1Options = dcc.Dropdown(options = [], placeholder = 'Search researchers', multi = False, id = "author1OptionsDropdown" + SUFFIX, 
        value = default_author or 'Ioannidis, John P.A.', searchable = True)
    generate_es_dropdown_callback("author1OptionsDropdown" + SUFFIX)
    generate_update_carsing_callback('author1OptionsDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX)
    generate_update_years_callback('careerORSingleYrA1' + SUFFIX, 'selectYrRadioA1' + SUFFIX, 'author1OptionsDropdown' + SUFFIX)
    output_ids = ['InfoAuthor1' + SUFFIX, 'FieldAuthor1' + SUFFIX, 'CountryAuthor1' + SUFFIX, 'InstitutionAuthor1' + SUFFIX]
    generate_update_cards_callback('selectYrRadioA1' + SUFFIX, output_ids, 'author1OptionsDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX,darkAccent1, highlight1)

    # =============== Author 2 Callbacks
    author2Options = dcc.Dropdown(options = [], placeholder = 'Search researchers', multi = False, id = "author2OptionsDropdown" + SUFFIX, 
    value = 'Bengio, Yoshua', searchable = True)
    generate_es_dropdown_callback("author2OptionsDropdown" + SUFFIX)
    generate_update_carsing_callback('author2OptionsDropdown' + SUFFIX, 'careerORSingleYrA2' + SUFFIX)
    generate_update_years_callback('careerORSingleYrA2' + SUFFIX, 'selectYrRadioA2' + SUFFIX, 'author2OptionsDropdown' + SUFFIX)
    output_ids = ['InfoAuthor2' + SUFFIX, 'FieldAuthor2' + SUFFIX, 'CountryAuthor2' + SUFFIX, 'InstitutionAuthor2' + SUFFIX]
    generate_update_cards_callback('selectYrRadioA2' + SUFFIX, output_ids, 'author2OptionsDropdown' + SUFFIX, 'careerORSingleYrA2' + SUFFIX, darkAccent1, highlight2)
   
    row2 = dbc.Container([
        dbc.Row([
            dbc.Col([author1Options, html.Div([html.Div(careerORSingleA1, className="ev-picker-left"), html.Span(className="ev-picker-sep"), html.Div(selectYrA1, className="ev-picker-right")], className="ev-picker ev-picker-inline") ], width = {'size':6}), 
            dbc.Col([author2Options, html.Div([html.Div(careerORSingleA2, className="ev-picker-left"), html.Span(className="ev-picker-sep"), html.Div(selectYrA2, className="ev-picker-right")], className="ev-picker ev-picker-inline") ], width = {'size':6}), 
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
    logTransf = daq.BooleanSwitch(label = 'Log transformed', labelPosition = 'bottom', id = 'logTransfToggleMain' + SUFFIX,
                                  className = 'ev-switch ev-switch-log')
    # =============== Toggle: % self-citations
    selfC = daq.BooleanSwitch(label = 'Exclude self-citations', labelPosition = 'bottom', id = 'selfCToggle' + SUFFIX,
                              className = 'ev-switch ev-switch-selfcite')
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
        )
    def update_author_figs_and_rank(career1, yr1, career2, yr2, ns, logTransf,group1_name, group2_name):
        '''
        group1_name: author name
        group2_name: author name
        '''
        if career1 == None or yr1 == None or career2 == None or yr2 == None: raise PreventUpdate
        # One value per output, in the order the outputs are declared.
        elif group1_name == None and group2_name == None: return ("No dataset selected", empty_fig, '')
        else:

            prefix1 = 'career' if career1 else 'singleyr'
            # exact=True: both names come from the author dropdowns.
            results = get_es_results(group1_name, prefix1, 'authfull', exact=True)
            data1 = {}
            data1_log = {}
            if results is not None:
                data1 = es_result_pick(results, 'data', None)
                data1_log  = data1[f'{prefix1}_{yr1}_log']
                data1 =  data1[f'{prefix1}_{yr1}']

            prefix2 = 'career' if career2 else 'singleyr'
            results = get_es_results(group2_name, prefix2, 'authfull', exact=True)
            data2 = {}
            data2_log = {}
            if results is not None:
                data2 = es_result_pick(results, 'data', None)
                data2_log  = data2[f'{prefix2}_{yr2}_log']
                data2 =  data2[f'{prefix2}_{yr2}']

            fig_list, new_rank_1, new_rank_2 = main_2_author_figs(data1, data1_log, data2, data2_log, group1_name, group2_name, ns, logTransf, g1c = g1c, g2c = g2c,
                author1_metrics = {},
                author2_metrics = {})
            for i in range(6): fig_list[i].update_layout(height = 200,width=200)
            fig_list[6].update_layout(height = 230, margin = {'t':20})

            # =============== Author 1 LEDD Display
            rankAuthor1_label = 'Rank of ' + group1_name if group1_name != None else 'No author selected'
            rankAuthor1 = daq.LEDDisplay(label = {"label":rankAuthor1_label, "style":{"color":highlight1, "font-size":"16px"}}, value = new_rank_1, backgroundColor = darkAccent1, color = highlight1, size = 70)
            
            # =============== Author 2 LEDD Display
            rankAuthor2_label = 'Rank of ' + group2_name if group2_name != None else 'No author selected'
            rankAuthor2 = daq.LEDDisplay(label = {"label":rankAuthor2_label, "style":{"color":highlight2, "font-size":"16px"}}, value = new_rank_2, backgroundColor = darkAccent1, color = highlight2, size = 70)

            figures = dbc.Row([
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[0]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[1]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[2]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[3]))], width = 2),
                dbc.Col([html.Center(dcc.Graph(figure = fig_list[4]))], width = 2), dbc.Col([html.Center(dcc.Graph(figure = fig_list[5]))], width = 2)]),
            c_img = dbc.Container([dbc.Row(html.Br()), dbc.Row(html.Br()), dbc.Row([dbc.Col(rankAuthor1), dbc.Col(rankAuthor2)]), dbc.Row(html.Br()), dbc.Row(dcc.Markdown(
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

    def main_2_author_figs(df_in, df_in_log, df2_in, df2_in_log, group1_name, group2_name, ns, logTransf, g1c = ['lightcoral', 'red'], g2c = ['lightblue', 'blue'], author1_metrics = {}, author2_metrics = {}):
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
        else:
            new_rank_2 = 0
            new_y_values_2 = [0]*7
            new_y_values_2_log = [0]*7

        def make_bar_traces(fig, y_in, y_in_log, colors, metric, name, logTransf = False, group_num = 1):
            if logTransf and metric != 'c' and metric != 'c (ns)': fig.add_trace(go.Bar(name = name, x = [metric], y = [y_in_log], text = [y_in], textposition = 'auto',marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
            else: fig.add_trace(go.Bar(name = name, x = [metric], y = [y_in], text = [y_in], textposition = 'auto',marker_color = colors[0], marker_line_width = 0), row = 1, col = group_num)
            hovertemp = 'count: %{text:.4s}<extra></extra> '
            # The label is the raw value, even on a log-transformed bar. It was
            # '%{text:.2s}', two significant figures, which printed an h-index
            # of 132 as "130". Counts are whole numbers; the hm-index and the
            # composite score are fractional, so they keep two decimals.
            texttemp = '%{text:.2f}' if metric.split(' ')[0] in ('hm', 'c') else '%{text:,d}'
            fig.update_traces(texttemplate = texttemp, hovertemplate = hovertemp)
            fig.update_layout(showlegend=False)
            return(fig)
        
        # metric titles
        subplot_titles = ['Number of citations<br>(NC)', 'H-index<br>(H)', 'Hm-index<br>(Hm)', 'Number of citations to<br>single authored papers<br>(NCS)', 
            'Number of citations to<br>single and first<br>authored papers<br>(NCSF)', 'Number of citations to<br>single, first and<br>last authored papers<br>(NCSFL)', 'Composite score (C)']
        fig_list = []
        for i, m in enumerate(metrics_list):
            if group1_name != None and group2_name == None: # If Author 1 only
                fig = make_subplots(rows = 1, cols = 1)
                fig = make_bar_traces(fig, y_in = new_y_values_1[i], y_in_log = new_y_values_1_log[i], colors = g1c, metric = m, name = group1_name, logTransf = logTransf, group_num = 1)
            elif group1_name == None and group2_name != None: # If Author 2 only
                fig = make_subplots(rows = 1, cols = 1)
                fig = make_bar_traces(fig, y_in = new_y_values_2[i], y_in_log = new_y_values_2_log[i], colors = g2c, metric = m, name = group2_name, logTransf = logTransf, group_num = 1)
            else: # If Author 1 and Author 2 exist
                fig = make_subplots(rows = 1, cols = 2, column_widths = [0.5, 0.5], shared_yaxes = True, horizontal_spacing = 0)
                fig = make_bar_traces(fig, y_in = new_y_values_1[i], y_in_log = new_y_values_1_log[i], colors = g1c, metric = m, name = group1_name, logTransf = logTransf, group_num = 1) 
                fig = make_bar_traces(fig, y_in = new_y_values_2[i], y_in_log = new_y_values_2_log[i], colors = g2c, metric = m, name = group2_name, logTransf = logTransf, group_num = 2)
            fig.update_layout(height = 500, title_x = 0.5, title_y = 0.95, title = {'text':subplot_titles[i], 'font':{'size':14}}, font = {'size':12, 'color':lightAccent1},
                plot_bgcolor = bgc, paper_bgcolor = bgc, margin = {'l':10, 'r':5, 'b':0, 't':100})
            fig.update_xaxes(automargin = True, showgrid = True, gridcolor = darkAccent2, linecolor = darkAccent2, tickmode = "array", tickvals = [])
            fig.update_layout(showlegend=False)
            fig_list.append(fig)
        return(fig_list, new_rank_1, new_rank_2)

    offcanvas2 = html.Div(
        [
            dbc.Offcanvas(
                dcc.Markdown(
                    '''
                **Controls**
                * **Log transformed**: plot the metrics on a logarithmic scale.
                * **Exclude self-citations**: leave out each researcher's citations to their own work.
                * Each researcher has their own dataset and year picker, so you can compare different editions. Options a researcher has no record in are greyed out.

                **Notes**
                * Researchers are ranked by the composite score C. The bars show the six metrics it is built from, for the selected dataset and year.
                * Career data covers everything up to the selected year; single-year data covers that year alone.
                * There is no single-year data for 2018.
                    '''
                ),
                id="offcanvas2",
                title="Compare two researchers",
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
        dbc.Row([dbc.Col(logTransf, width = {'offset':4, 'size':2}), dbc.Col(selfC, width = {'size':2}),dbc.Col(dbc.Button("More info", id="open-offcanvas2", n_clicks=0,
                                   className="ev-info-btn"),width = {'size':2})]), 
        dbc.Row(html.Br()), 
        metricsFigAuthor_c,
        dbc.Row(html.Br()), 
        offcanvas2,
        dbc.Row(dbc.Col(dbc.Container(id = '2author_figs' + SUFFIX), width = {'offset':1,'size':10}))])

    # ==========================================================================================
    # ==========================================================================================
    # Layout
    # ==========================================================================================
    # ==========================================================================================
    return(html.Div([
        dbc.Container(fluid = True, children = [
            html.Hr(),
            row2, 
            html.Hr(), 
            dls.GridFade(row3,color="#ECAB4C"), 
        ], className = 'ev-page'), 
    ]))
