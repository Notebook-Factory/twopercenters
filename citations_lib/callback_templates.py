from dash import html, dcc, callback, ctx #, Input, Output
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq
from citations_lib.create_fig_helper_functions import *
from citations_lib.utils import *

def generate_es_dropdown_callback(element_id):
    """
    Update options of the dropdown menu using Elasticsearch 
    type in realtime. 
    """
    @callback(
        Output(element_id, 'options'),
        [Input(element_id, 'search_value')],
    )
    def update_output(search_value):
        result = get_es_results(search_value, ['career', 'singleyr'], 'authfull')
        return es_result_pick(result, 'authfull')

    return dcc.Dropdown(
        options=[],
        placeholder='Start typing name & surname',
        multi=False,
        id=element_id,
        value='Ioannidis, John P.A.',
        searchable=True
    ), Input(element_id, 'value')

def generate_update_carsing_callback(input_id, output_id):
    """
    Update career/singleyr.
    """
    @callback(
        Output(output_id, 'options'),
        Output(output_id, 'value'),
        [Input(input_id, 'value')]
    )
    def update_author(value):
        if value is None:
            raise PreventUpdate
        else:
            result = get_es_results(value, ['career', 'singleyr'], 'authfull')
            if result is not None:
                if 'career' in list(result['_index']) and 'singleyr' in list(result['_index']):
                    opts = 'both'
                    val = True
                elif 'career' in list(result['_index']):
                    opts = 'career'
                    val = True
                elif 'singleyr' in list(result['_index']):
                    opts = 'singleyr'
                    val = False
                return update_cr_options(opts), val
            else:
                return [], [], False

    return update_author

def generate_update_years_callback(input_id, output_id, auth_dropdown_id):
    """
    Update years for a given author.
    """
    @callback(
        Output(output_id, 'options'),
        Output(output_id, 'value'),
        Input(input_id, 'value'),
        State(auth_dropdown_id, 'value')
    )
    def update_years(val, authname):

        if val is None:
            raise PreventUpdate
        else:
            prefix = 'career' if val else 'singleyr'
            results = get_es_results(authname, prefix, 'authfull')
            data = es_result_pick(results, 'data', None)
            yrs = update_auth_yrs(data.keys())
            return yrs, yrs[0]['value']

    return update_years

def generate_update_cards_callback(input_id, output_ids, auth_dropdown_id, career_singleyr_id,color1, color2):
    @callback(
        [Output(output_id, 'children') for output_id in output_ids],
        Input(input_id, 'value'),
        State(auth_dropdown_id, 'value'),
        State(career_singleyr_id, 'value'),
    )
    def update_cards(year, authname, is_career):
        if year is None:
            raise PreventUpdate
        else:
            prefix = 'career' if is_career else 'singleyr'
            results = get_es_results(authname, prefix, 'authfull')
            if results is not None:
                data = es_result_pick(results, 'data', None)
                names = get_inst_field_cntry(data, prefix, year)
                #print(names)
                stat = get_metric_summary(data, prefix, year, 'self%', 'median')
                #print(stat)
                cntry_full = coco.convert(names=names['cntry'], to='name_short')
                card1 = dbc.Card(html.Center(authname + ' (' + stat['own'] + ' % self-citation)'),
                                style={'color': color1, 'font-size': 18}, color=color2)
                card2 = dbc.Card(html.Center(names['field'] + ' (' + stat['field'] + ' % median self-citation)'),
                                style={'color': color1, 'font-size': 14}, color=color2)
                card3 = dbc.Card(html.Center(cntry_full + ' (' + stat['cntry'] + ' % median self-citation)'),
                                style={'color': color1, 'font-size': 14}, color=color2)
                card4 = dbc.Card(html.Center(names['inst'] + ' (' + stat['inst'] + ' % median self-citation)'),
                                style={'color': color1, 'font-size': 14}, color=color2)
                return card1, card2, card3, card4

    return update_cards