from dash import html, dcc, callback, ctx #, Input, Output
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq
from citations_lib.create_fig_helper_functions import *
from citations_lib.utils import *
import urllib

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
            yrs = update_auth_yrs(data.keys(),prefix)
            return yrs, yrs[0]['value']
    return update_years

def generate_update_cards_callback(input_id, output_ids, auth_dropdown_id, career_singleyr_id,color1, color2):
    @callback(
        [Output(output_id, 'children') for output_id in output_ids],
        Output(auth_dropdown_id, 'placeholder'),
        Input(input_id, 'value'),
        State(auth_dropdown_id, 'value'),
        State(career_singleyr_id, 'value'),
    )
    def update_cards(year, authname, is_career):
        if year is None:
            raise PreventUpdate
        else:
            prefix = 'career' if is_career else 'singleyr'
            when = 'career-long up to ' if is_career else 'in year '
            results = get_es_results(authname, prefix, 'authfull')
            if results is not None:
                data = es_result_pick(results, 'data', None)
                names = get_inst_field_cntry(data, prefix, year)
                txt1 = dcc.Markdown(f"Found in **{int(data[f'{prefix}_{year}']['np'])} papers**. Received **{int(data[f'{prefix}_{year}']['nc'])} citations** {when}{year}.",className = "lel")
                txt2 = dcc.Markdown(f"| **{int(data[f'{prefix}_{year}']['self%']*100)}% self citation** |  **{int(data[f'{prefix}_{year}']['h'])} [H-index](https://en.wikipedia.org/wiki/H-index)** | **{int(data[f'{prefix}_{year}']['hm'])} [Hm-index](https://arxiv.org/abs/0805.2000)** |",className = "lel")
                lnk = urllib.parse.quote(str(authname))
                cntry_full = coco.convert(names=names['cntry'], to='name_short')
                card1 = dbc.Card([dbc.CardLink(authname, href=f'https://scholar.google.ca/scholar?hl=en&as_sdt=0%2C5&q={lnk}&btnG=',target='_blank',style={"color":"black"})],
                                style={'color': color1, 'font-size': 18}, color=color2)
                card2 = dbc.Card(html.Center(names['inst'] + ', ' + names['field'] +  ', ' + cntry_full),
                                style={'color': color1, 'font-size': 14}, color=color2)
                card3 = dbc.Card([html.Center(txt1)],
                                style={'color': color1, 'font-size': 14}, color=color2)
                card4 = dbc.Card(html.Center(html.Center(txt2)),
                                style={'color': color1, 'font-size': 14}, color=color2)
                return card1, card2, card3, card4, "Start typing for new search | Displaying: " + authname.split(",")[0]

    return update_cards