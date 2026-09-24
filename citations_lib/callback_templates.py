from dash import html, dcc
from citations_lib.callbacks import callback
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import country_converter as coco
from citations_lib.utils import (
    author_options, es_result_pick, first_available_year, get_es_results,
    get_inst_field_cntry, update_auth_yrs, update_cr_options)
import urllib

def generate_es_dropdown_callback(element_id):
    """
    Update the dropdown's options as the user types.
    """
    @callback(
        Output(element_id, 'options'),
        [Input(element_id, 'search_value')],
    )
    def update_output(search_value):
        result = get_es_results(search_value, ['career', 'singleyr'], 'authfull')
        # Labels carry the institution and country: a bare list of names
        # cannot tell two people called `Zhu, Jianguo` apart, and there are
        # dozens of them. Typing an affiliation narrows the search itself.
        return author_options(result)

    return dcc.Dropdown(
        options=[],
        placeholder='Search researchers',
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
            # exact=True: `value` is a name already chosen in the dropdown.
            result = get_es_results(value, ['career', 'singleyr'], 'authfull',
                                    exact=True)
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
                return update_cr_options(opts, output_id), val
            else:
                # Two outputs, so two values: no kinds to offer, and the
                # toggle off. This returned three, which Dash rejects.
                return [], False

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
            # exact=True: `authname` came from the author dropdown.
            results = get_es_results(authname, prefix, 'authfull', exact=True)
            data = es_result_pick(results, 'data', None)
            if data is None:
                raise PreventUpdate
            yrs = update_auth_yrs(data.keys(), prefix)
            # The first option is the oldest edition, which most authors have
            # no data in; the first *enabled* one is the earliest year this
            # author actually appears in.
            return yrs, first_available_year(yrs)
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
            when = 'career-long, up to ' if is_career else 'in '
            # exact=True: `authname` came from the author dropdown.
            results = get_es_results(authname, prefix, 'authfull', exact=True)
            # A name that finds nobody has no cards to draw. This used to fall
            # off the end and return None, one value for five outputs; leaving
            # the cards as they are is what the year check above does too.
            if results is None:
                raise PreventUpdate
            else:
                data = es_result_pick(results, 'data', None)
                names = get_inst_field_cntry(data, prefix, year)
                txt1 = dcc.Markdown(f"Received **{int(data[f'{prefix}_{year}']['nc']):,} citations** {when}{year}.",className = "lel")
                txt2 = dcc.Markdown(f"| **{int(data[f'{prefix}_{year}']['self%']*100)}% self-citations** |  **{int(data[f'{prefix}_{year}']['h'])} [h-index](https://en.wikipedia.org/wiki/H-index)** | **{int(data[f'{prefix}_{year}']['hm'])} [hm-index](https://arxiv.org/abs/0805.2000)** |",className = "lel")
                lnk = urllib.parse.quote(str(authname))
                # coco raises on None rather than returning 'not found', and
                # 16,657 career rows have no country. Those show no country.
                if names['cntry'] is None:
                    cntry_full = None
                else:
                    cntry_full = coco.convert(names=names['cntry'],
                                              to='name_short')
                # Institution, field and country, from whichever of them the
                # row has: 10,967 career rows have no institution, and adding
                # None to a string raised.
                affiliation = [str(part) for part in
                               (names['inst'], names['field'], cntry_full)
                               if part is not None]
                card1 = dbc.Card(className='ev-fact-card', children=[dbc.CardLink(authname, href=f'https://scholar.google.ca/scholar?hl=en&as_sdt=0%2C5&q={lnk}&btnG=',target='_blank',style={"color":"black"})],
                                style={'color': color1, 'font-size': 18}, color=color2)
                card2 = dbc.Card(className='ev-fact-card', children=html.Center(', '.join(affiliation)),
                                style={'color': color1, 'font-size': 14}, color=color2)
                card3 = dbc.Card(className='ev-fact-card', children=[html.Center(txt1)],
                                style={'color': color1, 'font-size': 14}, color=color2)
                card4 = dbc.Card(className='ev-fact-card', children=html.Center(html.Center(txt2)),
                                style={'color': color1, 'font-size': 14}, color=color2)
                return card1, card2, card3, card4, str(authname)

    return update_cards
