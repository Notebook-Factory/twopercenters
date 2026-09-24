import dash
from dash import html, dcc, callback, dash_table, callback_context
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_loading_spinners as dls
import country_converter as coco

from citations_lib.auth_find import author_find_layout
from citations_lib.author_vs_author_layout import author_vs_author_layout
from citations_lib.author_vs_group_layout import author_vs_group_layout
from citations_lib.group_vs_group_layout import group_vs_group_layout
from citations_lib.single_author_layout import single_author_layout
from citations_lib.glowmap import glow_map
from citations_lib.top10 import top10_layout
from citations_lib.controls import kind_toggle
from citations_lib.place_cards import (
    city_card, country_card, institution_card, institution_links,
    notice_card, researcher_card, researcher_links)
from citations_lib.utils import (
    author_metrics, city_points, city_researchers, country_researcher_count,
    country_researchers, edition_author_count, es_result_pick,
    get_es_aggregate, get_es_results, institution_ror_for, name_is_shared,
    openalex_author, update_yr_options2)


# name is what dash.page_registry and the nav label show; without it Dash
# derives it from the module filename, which made this page "Home".
# title is what the browser tab says.
dash.register_page(__name__, path='/', name='Twopercenters',
                   title='Twopercenters')
SUFFIX = "HOME"

# Colours for the compare buttons below.
darkAccent1 = '#394459' # navy ground (Evidence)
lightAccent1 = '#00B4D8' # cyan leaf, primary accent

# The United States contributes 87,859 researchers to career-2024. Sending
# all of them made a 7.2 MB response that the browser had to parse and render,
# which is why clicking a large country looked like nothing happening. A page
# of names is what this table is for; the true total is shown beside it, and
# the spotlight search is the way to reach a specific person.
COUNTRY_ROW_LIMIT = 500

tbl  = dash_table.DataTable(
    id = 'instnametable',
    # Named, so the rows can carry who they are (AUTHOR_ID) without the id
    # becoming a column: with no columns given, the table shows every key.
    columns=[{'name': 'INSTITUTE', 'id': 'INSTITUTE'},
             {'name': 'RESEARCHER', 'id': 'RESEARCHER'}],
    fixed_rows={'headers': True},
    # These two were still the old ocre and a hardcoded rgb(50,50,50):
    # literals, so the palette sweep did not reach them, and they ignored the
    # theme. Inline styles take var(), so they follow it now.
    style_header={
        'backgroundColor': 'var(--ev-surface-2)',
        'color': 'var(--ev-text)',
        'fontWeight': '600',
        'border': 'none',
        'borderBottom': '1px solid var(--ev-surface-2)',
        'padding': '10px 12px',
    },
    style_data={
        'backgroundColor': 'transparent',
        'color': 'var(--ev-text)',
        'border': 'none',
        'borderBottom': '1px solid var(--ev-surface-2)',
    },
    # Runs the height of the map beside it. It was 300px with the summary
    # printed underneath; the summary is a card over it now.
    style_table={'height': '560px', 'overflowY': 'auto', 'display': 'none'},
    page_action='native',
    page_size=20,
    sort_action='native',
    # Dash marks the clicked cell with a pink outline, drawn as inline
    # borders on the cells around it, which the stylesheet cannot reach. The
    # tint in assets/style.css is the mark; the outline is turned off here.
    style_data_conditional=[
        {'if': {'state': state}, 'border': 'none',
         'borderBottom': '1px solid var(--ev-surface-2)'}
        for state in ('active', 'selected')
    ],
    style_cell={
        'height': 'auto',
        'textAlign': 'left',
        'maxWidth': '0',
        'whiteSpace': 'normal',
        'padding': '10px 12px',
        'fontSize': '0.9rem',
        'fontFamily': 'inherit',
    }
)


# Which slot of a summary vector each choice in the statistic dropdown reads.
# The vectors are [min, q1, median, q3, max, n].
STAT_INDEX = {'min': 0, '25': 1, 'median': 2, '75': 3, 'max': 4}


def _country_name(code):
    """A reader's name for an ISO3 code, or the code itself when
    country_converter does not know it, or None when there is no code."""
    if not code:
        return None
    name = str(coco.convert(names=str(code), to='name_short'))
    return str(code).upper() if name in ('not found', 'None') else name


def _no_statistic(name, is_career, yr):
    """What a summary says when the statistic dropdown has been cleared.

    The dropdown is clearable, and with nothing chosen there is no slot of
    the summary to read, so the summary asks for one instead of raising.
    """
    return notice_card(name, is_career, yr,
                       'Choose a summary statistic above the list to see '
                       'its numbers.')


def _no_record(name, is_career, yr):
    """What a summary says when there is nothing to summarise.

    A researcher need not have a record in every edition, an empty
    institution cell has no aggregate at all, and a country can be asked for
    an edition the dataset does not have while the year track catches up
    with the toggle.
    """
    return notice_card(name, is_career, yr,
                       'There is no record for this edition.')


@callback(
    Output('row-detail', 'children'),
    Output('row-card-subject', 'data'),
    [Input('instnametable', 'active_cell')],
    [State('glowYear_glowmap_', 'value'),
     State("careerORSingleYrRadio" + SUFFIX, 'value'),
     State("stats2", 'value'),
     State('instnametable', 'data'),
     # The rows on screen. active_cell['row'] counts these rather than the
     # rows in `data`, and the table pages and sorts in the browser, so on
     # page two or after a sort data[row] is somebody else.
     State('instnametable', 'derived_viewport_data')],
    prevent_initial_call='initial_duplicate')
def update_graphs(val, yr, iscar, sts, dt, viewport):
    """The card for a clicked row, and who it is about.

    The subject goes to a store rather than into the card, so the links,
    one of which is a call to OpenAlex, are filled by their own callback
    and the card draws without waiting for them.
    """
    if val is None:
        raise PreventUpdate
    prefix = 'career' if iscar else 'singleyr'

    # Before the table has reported what it is showing, the viewport is
    # empty and the first page is `data` as it was sent.
    shown = viewport if viewport else dt
    try:
        clicked = shown[val['row']]
    except (TypeError, IndexError, KeyError):
        raise PreventUpdate
    sel_type = val.get('column_id')
    if sel_type not in ('RESEARCHER', 'INSTITUTE'):
        # Only the two columns have a summary behind them.
        raise PreventUpdate
    selection = clicked.get(sel_type)

    if sel_type == 'RESEARCHER':
        author_id = clicked.get('AUTHOR_ID')
        subject = {'kind': 'researcher', 'name': selection,
                   'author_id': author_id, 'career': bool(iscar),
                   'year': str(yr)}
        record = _researcher_record(author_id, selection, prefix, yr)
        if not record:
            return _no_record(selection, iscar, yr), subject
        return researcher_card(selection, record, iscar, yr), subject

    subject = {'kind': 'institution', 'name': selection}
    if sts not in STAT_INDEX:
        return _no_statistic(selection, iscar, yr), subject
    data = get_es_aggregate('inst_name',selection,prefix)
    summary = (data or {}).get(f'{prefix}_{yr}')
    if not summary:
        return _no_record(selection or 'This institution', iscar, yr), subject
    return institution_card(selection, institution_ror_for(selection),
                            summary, STAT_LABELS[sts].capitalize(),
                            STAT_INDEX[sts], iscar, yr), subject


def _researcher_record(author_id, name, prefix, yr):
    """The clicked researcher's row for this edition, as the card reads it.

    The list knows which researcher each row is, so that id is read
    directly: several people can share a name, and looking the name up
    again could land on one of the others. A row without an id (a table
    filled some other way) falls back to the name.
    """
    if author_id:
        row = author_metrics(author_id, prefix, yr)
        if not row:
            return None
        return {'inst_name': row['institute'] or None,
                'cntry': _country_name(row['country_code']),
                'sm-field': row['field'] or None,
                'nc': row['nc'], 'h': row['h'], 'hm': row['hm'],
                'self%': row['self_pct']}
    results = get_es_results(name, prefix, 'authfull', exact=True)
    data = es_result_pick(results, 'data', None) if results is not None \
        else None
    record = (data or {}).get(f'{prefix}_{yr}')
    if not record:
        return None
    return dict(record, cntry=_country_name(record.get('cntry')))


@callback(
    Output('row-card-links', 'children'),
    Input('row-card-subject', 'data'),
    prevent_initial_call=True)
def row_card_links(subject):
    """Where the record lives elsewhere: OpenAlex for a researcher, and ROR
    for an institution matched there.

    OpenAlex is searched by name, so it can only be trusted when one
    researcher on the list has that name. Five people are published as
    "Kim, Tae-kyun"; a name match there would be a guess at which one.
    """
    if not subject:
        raise PreventUpdate
    if subject.get('kind') == 'researcher':
        name = subject.get('name')
        url = (openalex_author(name)
               if name and not name_is_shared(name) else None)
        return researcher_links(name, url)
    return institution_links(institution_ror_for(subject.get('name')))


@callback(
    Output('accordion', 'active_item', allow_duplicate=True),
    Output('spotlight-selection', 'data', allow_duplicate=True),
    Output('explore-preset', 'data', allow_duplicate=True),
    Input('row-card-explore', 'n_clicks'),
    State('row-card-subject', 'data'),
    prevent_initial_call=True)
def open_row_in_explore(clicks, subject):
    """The card's "Open in Explore": the same hand-off the Top 10 rows use,
    with the edition the reader was looking at."""
    # The button is rendered with the links, and Dash reports a newly
    # rendered button as a trigger with no clicks.
    if not clicks or not subject or subject.get('kind') != 'researcher':
        raise PreventUpdate
    return ('explore', subject['name'],
            {'career': bool(subject.get('career')),
             'year': str(subject.get('year') or ''), 'ns': False})


# The compare tabs and the Explore section are built when a reader opens
# them, and their builders declare their callbacks as they run. Dash only
# accepts callbacks declared before the first request, so each panel is built
# once here, at import. Later builds register nothing (citations_lib/callbacks.py).
for _build in (author_vs_author_layout, author_vs_group_layout,
               group_vs_group_layout, author_find_layout):
    _build()


# World map interactions


def _clicked_a_city(lat, lng, is_career, yr):
    """One city's researchers, in the same shape the country view uses.

    There is no aggregate for a city, because the summaries this dashboard
    keeps are per country, field and institution. What a city does have is
    the people in it, so the card says what can be counted directly and
    the table lists them, best score first.

    The point is identified by where it is rather than by what it is called,
    because a name is not unique even inside one country: Cleveland is in
    Ohio and in Tennessee, and there are four Oxfords on this map.
    """
    kind = 'career' if is_career else 'singleyr'
    rows, total = city_researchers(lat, lng, kind, yr,
                                   limit=COUNTRY_ROW_LIMIT)
    when = f"Career-long, up to {yr}" if is_career else f"Single year {yr}"
    if not rows:
        # A place on one edition's map can have nobody in another. This
        # used to raise PreventUpdate, which after a year change left the
        # old edition's list on screen beside a map of the new one, so the
        # panel says the place is empty in this edition instead.
        return (notice_card('No researchers here', is_career, yr,
                            'Nobody on the list works at this place in this '
                            'edition.'), [],
                f'<div class="danger"><center><strong>{when}</strong><br/>'
                f'No researchers on the list at this place.</center></div>',
                {'height': '560px', 'overflowY': 'auto', 'display': 'block'},
                [], None)
    points = [p for p in city_points(kind, int(yr))
              if abs(p['lat'] - lat) < 0.001 and abs(p['lng'] - lng) < 0.001]
    place = points[0] if points else None
    city = place['city'] if place else ''
    country_full = _country_name(place['country_code']) if place else None
    region = (place or {}).get('region')
    if place:
        summary = city_card(city, region, country_full, place, is_career, yr)
    else:
        summary = city_card(city or 'This place', region, country_full,
                            {'researchers': total, 'citations': None,
                             'papers': None, 'h': None}, is_career, yr)
    shown = len(rows)
    listing = (f'<strong>{shown:,}</strong> of <strong>{total:,}</strong> '
               f'researchers in <strong>{city}</strong>, highest score first'
               if total > shown
               else f'<strong>{total:,}</strong> researchers in '
                    f'<strong>{city}</strong>, highest score first')
    message = (f'<div class="danger"><center><strong>{when}</strong><br/>'
               f'{listing}'
               f'<br/><u>Click a name for details</u></center></div>')
    return (summary, rows, message,
            {'height': '560px', 'overflowY': 'auto', 'display': 'block'},
            [], None)


@callback(
    Output('place-summary', 'children'),
    Output('instnametable','data'),
    Output('cntrylabel','children'),
    Output('instnametable','style_table'),
    Output("instnametable", "selected_cells"),
    Output("instnametable", "active_cell"),
    Output('place-modal', 'is_open'),
    Input('glowPicked_glowmap_', 'value'),
    Input("careerORSingleYrRadio" + SUFFIX, 'value'),
    Input('glowYear_glowmap_', 'value'),
    Input('stats2', 'value'),
    State('instnametable', 'style_table'),
    prevent_initial_call='initial_duplicate'
    )
def click_on_map_update(val,is_career,yr,sts,table_style):
    """What the modal and the table show when a place is clicked.

    The map sends 'country|USA' or 'city|London|GBR', with a counter on the
    end so that clicking the same place twice is still a change Dash can
    see. A country reads its summary from the group_metrics aggregates in
    Postgres (through get_es_aggregate, which kept its old name); a city
    reads from institution_ror, which is where the coordinates that put the
    point on the map came from.

    The modal opens on a click and only on a click. Moving the year or the
    dataset refreshes what it holds, and the list, without opening it again.
    """
    if not val:
        raise PreventUpdate
    # Moving the year or the dataset refreshes whatever the panel is
    # showing, so that it never describes a different edition from the map.
    # If it is showing nothing, there is nothing to refresh: the queries
    # behind this take about a second each, and running them to fill a panel
    # nobody has opened is work for its own sake.
    picked = callback_context.triggered_id == 'glowPicked_glowmap_'
    showing = (table_style or {}).get('display') == 'block'
    if not picked and not showing:
        raise PreventUpdate
    parts = str(val).split('|')
    if len(parts) < 2:
        raise PreventUpdate
    open_modal = True if picked else dash.no_update
    if parts[0] == 'city':
        return _clicked_a_city(float(parts[1]), float(parts[2]), is_career,
                               yr) + (open_modal,)
    cr = 'career' if is_career else 'singleyr'
    cntry = parts[1].lower()
    # The code is what the lookups key on; the name is what a reader wants.
    cntry_full = _country_name(cntry)

    # This used to scroll the legacy `career`/`singleyr` Elasticsearch
    # indices and filter each document on a `years` field. Those indices
    # stop at 2021 and only survive on this machine as the latency
    # benchmark's baseline, so selecting 2022, 2023 or 2024 and clicking a
    # country listed nobody. country_researchers asks Postgres, where the
    # fact rows actually live, for the same thing.
    # The table gets a page's worth, not the whole country. The count below
    # is the true total, queried separately.
    total_in_country = country_researcher_count(cntry, cr, yr)
    career_all_c = country_researchers(cntry, cr, yr, limit=COUNTRY_ROW_LIMIT)
    total_authors = edition_author_count(cr, yr)

    # No summary for this edition, which is what a stale year looks like
    # (single year has no 2018), or no statistic chosen: the card says
    # which, and the list below is still filled.
    edition = (get_es_aggregate('cntry', cntry, cr) or {}).get(f'{cr}_{yr}')
    if not edition:
        summary = _no_record(cntry_full, is_career, yr)
    elif sts not in STAT_INDEX:
        summary = _no_statistic(cntry_full, is_career, yr)
    else:
        summary = country_card(cntry_full, total_in_country, total_authors,
                               STAT_LABELS[sts].capitalize(), edition,
                               STAT_INDEX[sts], is_career, yr)

    txt = f"Career-long, up to {yr}" if is_career else f"Single year {yr}"
    shown = len(career_all_c)
    if total_in_country > shown:
        listing = (f'<strong>{shown:,}</strong> of '
                   f'<strong>{total_in_country:,}</strong> researchers in '
                   f'<strong>{cntry_full}</strong>, A to Z')
    else:
        listing = (f'<strong>{total_in_country:,}</strong> researchers in '
                   f'<strong>{cntry_full}</strong>, A to Z')
    msg = (f'<div class="danger"><center><strong>{txt}</strong><br/>'
           f'{listing}'
           f'<br/><span class="ev-of-total">{total_authors:,} worldwide '
           f'in this edition</span>'
           f'<br/><u>Click a name for details</u></center></div>')
    return (summary, career_all_c, msg,
            {'height': '560px', 'overflowY': 'auto', 'display': 'block'},
            [], None, open_modal)


@callback(
    Output('worldtitle', 'style'),
    Input('instnametable', 'style_table'))
def explanation_style(table_style):
    """The explanation of the map fills the pane until a place is clicked;
    after that the pane is the list of that place, in the same spot."""
    if (table_style or {}).get('display') == 'block':
        return {'display': 'none'}
    return {}


@callback(
    Output('place-modal', 'is_open', allow_duplicate=True),
    Input('place-modal-close', 'n_clicks'),
    prevent_initial_call=True)
def close_place_modal(clicks):
    """Close the modal; the list is already beside the map."""
    if not clicks:
        raise PreventUpdate
    return False


# The year the explanation below uses in its examples. It follows the most
# recent career edition, so loading a new edition moves it without an edit
# here.
_, _MAP_DEFAULT_YEAR = update_yr_options2(True)

# The map itself is the echarts map in citations_lib/glowmap.py. What this
# page adds are the controls the tables beside it also read: the dataset
# toggle and the summary statistic.
#
# The dataset toggle is two icons rather than the words "Career" and
# "Single year". Every page's toggle is built by the same helper, so the
# control that means the same thing in six places also reads the same in all
# six; see citations_lib/controls.py for why it is icons.
careerORSingleYr = kind_toggle("careerORSingleYrRadio" + SUFFIX)


zortt = dcc.Dropdown(id='stats2',options={'min':'Minimum (individual)','25':'25th percentile (group)','median':'Median (group)','75':'75th percentile (group)','max':'Maximum (individual)'},value='median')
# How the chosen statistic is named in the summary it produces.
STAT_LABELS = {'min': 'minimum', '25': '25th percentile', 'median': 'median',
               '75': '75th percentile', 'max': 'maximum'}
# The reference notes beside the map. What the map is and how to start is said
# by the hint over the map itself, so it is not repeated here. The first note
# is open from the start: which of the two records is on screen changes every
# number on the page, and it is the thing a reader most often gets wrong.
def _note(icon, title, body, open_=False):
    return html.Div(html.Details([
        html.Summary([html.I(**{'data-lucide': icon}), html.Strong(title)]),
        *body,
    ], open=open_), className='danger')


def _kind_chip(icon, active):
    """The dataset toggle's icon, drawn as the toggle draws it."""
    return html.Span(html.Span(className=f'ev-ic ev-ic-{icon}'),
                     className='ev-kind-chip'
                               + (' ev-kind-chip-on' if active else ''))


_COMPOSITE = r"""
$$
C \;=\; \sum_{k=1}^{6} \frac{\ln(1 + x_k)}{\ln(1 + \max x_k)}
$$
"""

map_notes = html.Div([
    _note('help-circle', 'Career vs single year', [
        html.P('The data holds two records for each researcher. The pair of '
               'icons above the map switches between them.'),
        html.P([_kind_chip('history', True), html.Span([
            html.Strong('Career-long'),
            ' counts everything up to the selected year, so ',
            html.Strong(f'career, {_MAP_DEFAULT_YEAR}'),
            ' is an h-index built over a whole career up to '
            f'{_MAP_DEFAULT_YEAR}.'])], className='ev-kind-line'),
        html.P([_kind_chip('calendar', False), html.Span([
            html.Strong('Single year'),
            ' counts that year alone, so ',
            html.Strong(f'single year, {_MAP_DEFAULT_YEAR}'),
            f' is the h-index for {_MAP_DEFAULT_YEAR} only. There is no '
            'single-year data for 2018, so that year disappears from the '
            'track when you switch.'])], className='ev-kind-line'),
    ], open_=True),
    _note('sigma', 'How the composite score works', [
        html.P('The list is ranked by the composite score C. It adds up six '
               'indicators: citations, the h-index, the hm-index, and '
               'citations to single-authored, single- or first-authored, and '
               'single-, first- or last-authored papers.'),
        dcc.Markdown(_COMPOSITE, mathjax=True, className='ev-formula'),
        html.P('Each term is one indicator on a log scale, divided by the '
               'largest value in the edition on the same scale. So each term '
               'is between 0 and 1, and C is between 0 and 6. With '
               'self-citations excluded, the same sum runs on the counts '
               'without them.'),
    ]),
    _note('map-pin', 'Why some researchers are missing from Cities', [
        html.P(['The published data gives each institution as a name and a '
                'country, with no city or coordinates. The cities come from '
                'matching those names against ',
                html.A('ROR', href='https://ror.org', target='_blank'),
                ', which places about seven in ten researchers. ',
                html.Strong('Countries'),
                ' has no such gap, because every row has a country.']),
    ]),
    _note('list', 'Metric abbreviations', [html.Ul([
        html.Li([html.B('nc:'), ' number of citations']),
        html.Li([html.B('h:'), ' ', html.A(
            'h-index', href='https://en.wikipedia.org/wiki/H-index',
            target='_blank')]),
        html.Li([html.B('hm:'), ' ', html.A(
            'hm-index',
            href='https://ideas.repec.org/a/eee/infome/v2y2008i3p211-216.html',
            target='_blank'), ', the h-index adjusted for co-authorship']),
        html.Li([html.B('ncs:'), ' citations to single-authored papers']),
        html.Li([html.B('ncsf:'),
                 ' citations to single- or first-authored papers']),
        html.Li([html.B('ncsfl:'),
                 ' citations to single-, first- or last-authored papers']),
        html.Li([html.B('c:'), ' the composite score, which sets the ranking']),
    ])]),
], className='ev-map-notes')


# The table, and the card that opens over it.
#
# The detail for a clicked row used to print under the table, which pushed
# the table up and meant reading one row cost you the sight of the others.
# It is a card over the list now, dismissable, so the table can run the full
# height of the map beside it.
zart = dls.Ring(
    html.Div([
        dcc.Markdown(id='cntrylabel', children="",
                     dangerously_allow_html=True),
        tbl,
        html.Div(id='worldtitle', children=map_notes),
    ], className="ev-list-stack"),
    color="#ECAB4C", width=270)


# The card a clicked row opens, over the map rather than over the list it
# was clicked in: the list is where the reader is working, and covering it
# takes away the thing they are working through.
row_card = html.Div(
    [
        html.Button(html.Span(className="ev-ic ev-ic-x"),
                    id="row-card-close", n_clicks=0,
                    className="ev-row-card-close", title="Close"),
        html.Div(id='row-detail'),
        # Filled by row_card_links after the card is drawn, because the
        # OpenAlex lookup is a call to somebody else's server.
        html.Div(id='row-card-links', className='ev-id-links ev-row-links'),
        dcc.Store(id='row-card-subject'),
    ],
    id="row-card", className="ev-row-card", style={'display': 'none'},
)


# The place a reader clicked on the map, once, over the page. Closing it
# leaves the list of that place's researchers beside the map, which is what
# the click was for; the numbers are a summary to read on the way there.
place_modal = dbc.Modal(
    dbc.ModalBody([
        html.Button(html.Span(className="ev-ic ev-ic-x"),
                    id="place-modal-close", n_clicks=0,
                    className="ev-row-card-close", title="Close",
                    **{"aria-label": "Close"}),
        html.Div(id='place-summary'),
    ], className='ev-place-body'),
    id='place-modal',
    is_open=False,
    centered=True,
    size='lg',
    contentClassName='ev-place-modal',
    backdrop=True,
)


# ============================================================================
# One current author across the whole dashboard
# ----------------------------------------------------------------------------
# Picking someone in any panel should carry to the others: it is the same
# question asked four ways, and retyping the name in each was busywork.
#
# The selection lives in a store rather than being written from one dropdown
# into another. Panels are built on demand, so a callback writing into a
# dropdown that is not mounted yet would fail; seeding the layout at build
# time cannot. The one panel that is always mounted, the trends section, is
# kept in step by the callback below.
# ============================================================================

AUTHOR_PICKERS = [
    "authorOptionsDropdown_single_author",
    "author1OptionsDropdown_author_find_",
    "author1OptionsDropdown_author_vs_author",
    "group1ListDropdown_author_vs_group",
]


@callback(
    Output("spotlight-selection", "data", allow_duplicate=True),
    [Input(picker, "value") for picker in AUTHOR_PICKERS],
    prevent_initial_call=True,
)
def remember_author(*values):
    """Record whichever picker was just changed as the current author."""
    triggered = callback_context.triggered_id
    if triggered not in AUTHOR_PICKERS:
        raise PreventUpdate
    chosen = values[AUTHOR_PICKERS.index(triggered)]
    if not chosen:
        raise PreventUpdate
    return chosen


@callback(
    Output("authorOptionsDropdown_single_author", "value"),
    Input("spotlight-selection", "data"),
    State("authorOptionsDropdown_single_author", "value"),
    prevent_initial_call=True,
)
def sync_trends_author(chosen, current):
    """Keep the always-mounted trends picker on the current author.

    Returning the value it already holds would be a no-op anyway, but
    PreventUpdate says so explicitly and keeps this off the callback graph
    when nothing changed.
    """
    if not chosen or chosen == current:
        raise PreventUpdate
    return chosen


# The instruction that used to sit at the bottom of the right-hand column,
# lifted into a glass card over the map. It says one thing, once, and then
# gets out of the way; leaving it in the column meant it occupied space that
# belongs to the country results for the whole session.
map_hint = html.Div(
    [
        html.Button(
            html.Span(className="ev-ic ev-ic-x"),
            id="map-hint-close", n_clicks=0, className="ev-hint-close",
            title="Dismiss",
        ),
        html.Div(
            [
                html.I(**{"data-lucide": "mouse-pointer-click"}),
                html.Div(
                    [
                        html.Div("Click a place to see who is there",
                                 className="ev-hint-title"),
                        html.Div(
                            "On Cities, clicking a point lists the "
                            "researchers who work there, highest score "
                            "first. On Countries, clicking a country lists "
                            "all of its researchers. Both follow the dataset "
                            "and year you have selected.",
                            className="ev-hint-body"),
                    ]
                ),
            ],
            className="ev-hint-row",
        ),
    ],
    id="map-hint",
    className="ev-hint",
)


@callback(
    Output("map-hint", "style"),
    Input("map-hint-close", "n_clicks"),
    Input('glowPicked_glowmap_', 'value'),
    Input('row-detail', 'children'),
    prevent_initial_call=True,
)
def dismiss_map_hint(_close, _clicked, _row):
    """Hide the hint once it has been read, or made redundant.

    Clicking a country is included deliberately: at that point the user has
    done the thing the hint asks for, so the card has nothing left to say.
    Opening a researcher's detail counts too, and it also keeps the two
    cards from sitting on top of each other in the same corner.

    This sets an inline style rather than swapping in a class that sets
    opacity: 0. The class was being applied correctly, and pointer-events from
    it took effect, but the computed opacity stayed at 1, so the card went
    inert while still being visible, which looked like a close button that did
    nothing. An inline display:none cannot be out-ranked by a stylesheet rule.
    """
    return {"display": "none"}


offcanvas = html.Div(
    [
        dbc.Offcanvas(
            dcc.Markdown(
                dangerously_allow_html=True,
                children='''
                #### Top 2% researchers

                <div class="ev-byline">Nadia Blostein, Agah Karakuzu, and Nikola Stikov</div>

                ---

                Explore the database of the top 2% most-cited researchers [(Ioannidis et al. 2019)](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3000384&page=69&page=9&page=104&page=7&). For each researcher it gives standardized citation counts, the h-index, the co-authorship-adjusted hm-index, citations by authorship position, and a composite score that sets the ranking.

                The data is openly available from the [Elsevier Data Repository](https://elsevier.digitalcommonsdata.com/datasets/btchxktzyw/5).

                ---
                The dashboard and its database are hosted by [Evidence](https://evidencepub.io).

                If you would like to share a data application alongside your research articles, contact us at `info@evidencepub.io`.

                Built with Plotly Dash. The data is served from Postgres, and Elasticsearch runs the name search. Source code by the [NotebookFactory](https://github.com/Notebook-Factory/twopercenters).
                '''
            ),
            id="offcanvas",
            title="Twopercenters dashboard",
            # Starts closed. assets/spotlight.js opens it once per browser on a
            # first visit and records that it has been seen; after that the
            # More info button is the way back to it. Opening it over the page
            # on every single load, with a backdrop dimming everything behind
            # it, made the dashboard unusable until dismissed.
            is_open=False,
            className="ev-intro",
        ),
    ]
)


@callback(
    Output("row-card", "style"),
    Input("row-detail", "children"),
    Input("row-card-close", "n_clicks"),
    prevent_initial_call=True,
)
def show_the_row_card(_summary, _close):
    """Open the card when there is something new to read in it, close it on
    the button. Which of the two happened is read from the trigger rather
    than from the values, because a summary can legitimately be the same
    text twice running."""
    closing = callback_context.triggered_id == "row-card-close"
    return {'display': 'none'} if closing else {'display': 'block'}


@callback(
    Output("offcanvas", "is_open"),
    Input("off", "n_clicks"),
    [State("offcanvas", "is_open")],
)
def toggle_offcanvas(n1, is_open):
    if n1:
        return not is_open
    return is_open

# Served out of assets/ rather than hotlinked from GitHub, so the mark still
# renders if github.com is unreachable from the deployment.
EVIDENCE_LOGO = "/assets/evidence-logo.png"
EVIDENCE_URL = "https://evidencepub.io"
# The mark and the wordmark sit together on the left as one brand lockup,
# rather than being spread apart by justify='around' inside a container that
# CSS was squeezing into the left third of the bar. dark=True so Bootstrap
# picks light foreground colours to go with the dark ground set in style.css.
# One row, three groups, one height. The previous version stacked a wordmark
# over an attribution line inside a Bootstrap grid Row, which made the bar tall
# and ragged and left the right-hand buttons floating against nothing. Here the
# brand is a fixed-height lockup, the actions are a single flex group, and
# every control in the bar is 36px so they share a baseline.
dede = dbc.Navbar(
    dbc.Container(
        [
            html.Div(
                [
                    html.A(html.Img(src=EVIDENCE_LOGO, className="ev-mark"),
                           href="/"),
                    html.Div(
                        [
                            html.A("Twopercenters", href="/",
                                   className="ev-wordmark"),
                            html.Span(
                                [
                                    "developed and hosted by ",
                                    html.A("Evidence", href=EVIDENCE_URL,
                                           target="_blank",
                                           className="ev-attrib-link"),
                                ],
                                className="ev-tagline",
                            ),
                        ],
                        className="ev-brand-text",
                    ),
                ],
                className="ev-brand",
            ),
            html.Div(
                [
                    dbc.Button(
                        [html.I(**{"data-lucide": "search"}),
                         html.Span("Search researchers",
                                   className="ev-search-label"),
                         html.Kbd("⌘K", className="ev-kbd")],
                        id="spotlight-open", className="ev-nav-search",
                        n_clicks=0),
                    html.Span(className="ev-nav-sep"),
                    dbc.Button([html.I(**{"data-lucide": "user"}), "Explore"],
                               id="jump-explore", className="ev-nav-btn",
                               n_clicks=0),
                    dbc.Button([html.I(**{"data-lucide": "trophy"}),
                                "Top 10"],
                               id="jump-top10", className="ev-nav-btn",
                               n_clicks=0),

                    dbc.Button([html.I(**{"data-lucide": "users"}), "Compare"],
                               id="jump-compare", className="ev-nav-btn",
                               n_clicks=0),
                    dbc.Button([html.I(**{"data-lucide": "trending-up"}),
                                "Trends"],
                               id="jump-trends", className="ev-nav-btn",
                               n_clicks=0),
                    html.Span(className="ev-nav-sep"),
                    # A mask icon rather than a lucide <i>. Those are
                    # replaced in the DOM after render, and a click that
                    # starts on an element which is swapped before the mouse
                    # comes up never becomes a click at all, which is why
                    # this button and the hint's close button both needed
                    # pressing twice.
                    dbc.Button(html.Span(className="ev-ic ev-ic-info"),
                               id='off', n_clicks=0,
                               className="ev-nav-btn ev-nav-icon",
                               title="About this data"),
                    dbc.Button(id="theme-toggle", n_clicks=0,
                               className="ev-theme-toggle",
                               title="Switch between dark and light"),
                ],
                className="ev-nav-actions",
            ),
        ],
        className="ev-navbar-inner",
        fluid=True,
    ),
    dark=True,
    sticky="top",
)


# Button id -> the section it opens, by item_id rather than by position in
# ACCORDION_SECTIONS. Reordering the sections used to silently repoint these:
# "Compare" returned SECTIONS[0], so once "explore" took first place the
# multi-person icon opened the single-researcher section.
_JUMP_TARGETS = {
    "jump-explore": "explore",
    "jump-top10": "top10",
    "jump-trends": "trends",
    "jump-compare": "compare",
}


@callback(
    Output("accordion", "active_item"),
    Input("jump-explore", "n_clicks"),
    Input("jump-top10", "n_clicks"),
    Input("jump-trends", "n_clicks"),
    Input("jump-compare", "n_clicks"),
    prevent_initial_call=True,
)
def jump_to_section(_explore, _top10, _trends, _compare):
    """Open the section whose navbar button was pressed.

    Which button fired is read from the trigger rather than from the click
    counts, because comparing counts breaks as soon as one button is pressed
    twice in a row.
    """
    target = _JUMP_TARGETS.get(callback_context.triggered_id)
    if target is None:
        raise PreventUpdate
    return target


# Opening the section is not the same as going to it.
#
# "explore" is the section the accordion starts on, so pressing Explore set
# active_item to the value it already held: the callback above returned, Dash
# saw no change, and nothing at all happened on screen. The other two buttons
# did open their section, but left the reader at the top of the page with the
# change happening somewhere below the fold.
#
# Scrolling belongs in the browser rather than in a server callback, and it is
# safe here in a way it was not in the picker: this runs on a click, not on
# every DOM mutation.
dash.clientside_callback(
    """
    function (explore, trends, compare) {
        var trigger = (dash_clientside.callback_context.triggered || [])[0];
        if (!trigger || !trigger.value) { return window.dash_clientside.no_update; }
        var order = {'jump-explore': 0, 'jump-top10': 1, 'jump-trends': 2,
                     'jump-compare': 3};
        var index = order[trigger.prop_id.split('.')[0]];
        if (index === undefined) { return window.dash_clientside.no_update; }

        // After the section has opened, so the header is where it will stay.
        setTimeout(function () {
            var items = document.querySelectorAll('#accordion .accordion-item');
            var item = items[index];
            if (!item) { return; }
            // The toolbar is sticky, so scrolling the header to the top of the
            // viewport would put it underneath.
            var bar = document.querySelector('.ev-toolbar');
            var clearance = (bar ? bar.getBoundingClientRect().height : 0) + 14;
            var top = item.getBoundingClientRect().top + window.scrollY;
            window.scrollTo({top: Math.max(0, top - clearance),
                             behavior: 'smooth'});
        }, 160);
        return '';
    }
    """,
    Output("jump-sink", "children"),
    Input("jump-explore", "n_clicks"),
    Input("jump-top10", "n_clicks"),
    Input("jump-trends", "n_clicks"),
    Input("jump-compare", "n_clicks"),
    prevent_initial_call=True,
)


def _map_with_kind_toggle():
    """The map, with the career/single-year toggle in its header.

    The toggle belongs to this page rather than to the map module, because
    the tables beside the map read it too. It goes into the same row as the
    granularity and the measure, so the three read as one set of controls
    rather than one control and a pair of them at opposite ends.
    """
    built = glow_map()
    for node in built.children:
        if getattr(node, 'className', '') == 'ev-glow-head':
            node.children = [html.Div(
                [careerORSingleYr] + list(node.children[1].children),
                className='ev-glow-measures')]
            break
    return built


# A two-pane body: map on the left, the list and its summary on the right.
# They are cards with room around them, rather than two grid columns butted
# together against the page.
navigation_row = html.Div(
    [
        dbc.Row(
            [
                dbc.Col(html.Div([_map_with_kind_toggle(), map_hint,
                                  row_card],
                                 className="ev-map-pane"),
                        width=8),
                dbc.Col(html.Div([
                    html.Div([
                        html.Span('Summary statistic',
                                  className='ev-pane-label'),
                        zortt,
                    ], className='ev-pane-head'),
                    zart,
                ], className='ev-list-pane'), width=4),
            ],
            className="ev-panes",
        ),
    ],
    className="ev-stage",
)

tabs = [
    dbc.Tabs(
        [
            # "comparison" on three of four labels is the word they have in
            # common, so it carries no information and only makes the row wide
            # enough to wrap.
            dbc.Tab(label="Author vs author", tab_id="tab-1"),
            dbc.Tab(label="Author vs group", tab_id="tab-2"),
            dbc.Tab(label="Group vs group", tab_id="tab-3"),
        ],
        id="tabs",
        active_tab="tab-1",
    ),
    html.Div(id="content"),
]

@callback(Output("content", "children"), [Input("tabs", "active_tab")],
          State("spotlight-selection", "data"))
def switch_tab(at, picked):
    # Each panel is built on demand, so the current author is handed to it at
    # build time rather than written into its dropdown afterwards: the
    # dropdown does not exist until this returns. Group vs group has no author
    # side, so it takes nothing.
    if at == "tab-1":
        return html.Center(author_vs_author_layout(picked))
    elif at == "tab-2":
        return html.Center(author_vs_group_layout(picked))
    elif at == "tab-3":
        return html.Center(group_vs_group_layout())


@callback(Output("explore-content", "children"),
          Input("accordion", "active_item"),
          State("spotlight-selection", "data"))
def build_explore(active, picked):
    """Build the Explore section when it is opened.

    Same on-demand rule as the tabs: the panel is built here rather than at
    import, so a name chosen in the spotlight is handed to it at build time
    instead of a callback writing into a dropdown that does not exist yet.
    """
    if active != ACCORDION_SECTIONS[0][0]:
        raise PreventUpdate
    return html.Center(author_find_layout(picked) if picked
                       else author_find_layout())


# item_id lets the navbar's jump buttons open a section directly. The
# "(toggle)" the titles used to carry is gone: the chevron and the hover state
# say it, and a title that has to explain its own widget is a sign the widget
# is not reading as one.
ACCORDION_SECTIONS = [
    ("explore", "Explore one researcher",
     "Every metric for one researcher, against the field they work in",
     "user"),
    ("top10", "Top 10 researchers",
     "Who leads the selected edition, and which indicator puts them there",
     "trophy"),
    ("trends", "One researcher over time",
     "How a single researcher's metrics move across editions",
     "trending-up"),
    ("compare", "Compare researchers and groups",
     "Put two researchers, or a researcher and a group, side by side",
     "users"),
]

# What each section holds. Keyed by item_id for the same reason the jump
# buttons are: the items used to be written out one by one against
# ACCORDION_SECTIONS[0], [1] and [2], so inserting a section silently gave
# three of them somebody else's title.
_SECTION_CONTENT = {
    "explore": lambda: html.Div(id="explore-content"),
    "top10": top10_layout,
    "trends": single_author_layout,
    "compare": lambda: html.Div(tabs),
}


accordion = html.Div(
    dbc.Accordion(
        [
            dbc.AccordionItem(
                [_SECTION_CONTENT[item_id]()],
                title = title,
                item_id = item_id,
                # The section's own accent is keyed off this class rather
                # than off its position. assets/style.css used to colour the
                # sections with :nth-of-type, so inserting Top 10 as the
                # second one handed every section below it the colour of its
                # neighbour while the navbar buttons kept theirs.
                class_name = f'ev-section ev-section-{item_id}',
            )
            for item_id, title, _blurb, _icon in ACCORDION_SECTIONS
        ],
        flush = False,
        id='accordion',
        active_item = ACCORDION_SECTIONS[0][0],
    ),
    id='accordion-anchor',
)

# Clientside callbacks need somewhere to return to; this is that and nothing
# else.
jump_sink = html.Div(id="jump-sink", style={"display": "none"})


def _footer_link(icon, label, href):
    """One labelled link with a Lucide glyph in front of it."""
    return html.A(
        [html.I(**{"data-lucide": icon}), html.Span(label)],
        href=href, target="_blank", className="ev-foot-link",
    )


# A sign-off, not a second masthead: the mark on the left, the links beside it,
# the wordmark bottom-right. Both marks are served from assets/ rather than
# hotlinked, so the footer still renders if evidencepub.io is unreachable from
# the deployment.
footer = html.Footer(
    id='footer',
    className='ev-footer',
    children=[
        html.Div(
            [
                html.A(
                    [
                        # Two files rather than a CSS filter: the mark's body
                        # is one class in the SVG (#394459, the same navy as
                        # the dark page), and a light page needs that piece
                        # white while the coloured leaves stay as they are. A
                        # filter cannot single it out. CSS shows one or the
                        # other per theme.
                        # White body on the dark theme, navy body on the
                        # light one: the body is the same navy as the dark
                        # page, so it vanishes there unless it is swapped.
                        html.Img(src="/assets/evidence-mark-light.svg",
                                 className="ev-foot-mark ev-only-dark",
                                 alt="Evidence"),
                        html.Img(src="/assets/evidence-mark.svg",
                                 className="ev-foot-mark ev-only-light",
                                 alt="Evidence"),
                    ],
                    href="https://evidencepub.io", target="_blank",
                    className="ev-foot-brand",
                ),
                html.Div(
                    [
                        _footer_link("book-open", "Paper",
                                     "https://journals.plos.org/plosbiology/"
                                     "article?id=10.1371/journal.pbio.3000384"),
                        _footer_link("database", "Elsevier data",
                                     "https://elsevier.digitalcommonsdata.com/"
                                     "datasets/btchxktzyw/5"),
                        _footer_link("code", "Source code",
                                     "https://github.com/Notebook-Factory/twopercenters"),
                        _footer_link("mail", "Contact",
                                     "mailto:info@evidencepub.io"),
                    ],
                    className="ev-foot-links",
                ),
            ],
            className="ev-foot-top",
        ),
        html.Div(
            [
                html.Span("Top 2% most-cited researchers",
                          className="ev-foot-note"),
                html.A(
                    html.Img(src="/assets/evidence-label.svg",
                             className="ev-foot-label", alt="Evidence"),
                    href="https://evidencepub.io", target="_blank",
                ),
            ],
            className="ev-foot-bottom",
        ),
    ],
)


# ============================================================================
# Spotlight search
# ----------------------------------------------------------------------------
# The author typeahead used to live only inside a tab inside a collapsed
# accordion, so the dashboard's main verb was three clicks down. This lifts it
# to a command-palette overlay: Cmd-K / Ctrl-K anywhere, or the Search button
# in the navbar. It reuses get_es_results against the `authors` alias, which is
# the same fuzzy search the in-tab dropdown uses, so a typo still finds the
# author. Picking a result opens the Explore section on that author.
# ============================================================================

spotlight = dbc.Modal(
    [
        dbc.ModalBody(
            [
                # A plain text input, not a dcc.Dropdown. The dropdown could
                # not be focused reliably on open (its real <input> is nested
                # and remounts as options arrive), and it draws a form control
                # where Spotlight draws a bare line of text. This is one big
                # borderless field plus a result list underneath, which is the
                # shape people already know.
                dcc.Input(
                    id="spotlight-input",
                    type="text",
                    value="",
                    placeholder="Search researchers…",
                    autoComplete="off",
                    debounce=False,
                    autoFocus=True,
                    className="ev-spotlight-input",
                ),
                html.Div(id="spotlight-results",
                         className="ev-spotlight-results"),
                html.Div(
                    [
                        html.Span("Misspellings are fine."),
                        html.Span("esc to close", className="ev-spotlight-esc"),
                    ],
                    className="ev-spotlight-hint",
                ),
                # "esc to close" told a reader how to leave but gave them
                # nothing to click, which is a keyboard instruction standing
                # in for a control. Anyone reaching for a mouse, or on a
                # touch screen where there is no esc key at all, was stuck.
                html.Button("\u00d7", id="spotlight-close", n_clicks=0,
                            title="Close", **{"aria-label": "Close search"},
                            className="ev-overlay-close"),
            ],
            className="ev-spotlight-body",
        ),
    ],
    id="spotlight",
    is_open=False,
    centered=False,
    size="lg",
    contentClassName="ev-spotlight",
    backdrop=True,
)

# How many names the overlay offers. Spotlight-style lists are short on
# purpose: a long list is a second search problem.
SPOTLIGHT_LIMIT = 8


@callback(
    Output("spotlight-results", "children"),
    Input("spotlight-input", "value"),
)
def spotlight_results(term):
    """The same fuzzy search the in-tab dropdown runs, as a clickable list."""
    if not term or len(term) < 2:
        return []
    names = es_result_pick(
        get_es_results(term, ['career', 'singleyr'], 'authfull'), 'authfull')
    if not names:
        return html.Div("No researchers match that name.",
                        className="ev-spotlight-empty")
    return [
        html.Button(
            name,
            id={"type": "spotlight-hit", "index": i},
            className="ev-spotlight-hit",
            n_clicks=0,
        )
        for i, name in enumerate(names[:SPOTLIGHT_LIMIT])
    ]


@callback(
    Output("spotlight", "is_open"),
    Input("spotlight-open", "n_clicks"),
    Input("spotlight-close", "n_clicks"),
    Input({"type": "spotlight-hit", "index": ALL}, "n_clicks"),
    State("spotlight", "is_open"),
    prevent_initial_call=True,
)
def toggle_spotlight(_clicks, _close, hits, is_open):
    """Open on the navbar button, close on the X or once a result is picked."""
    triggered = callback_context.triggered_id
    if triggered == "spotlight-open":
        return not is_open
    if triggered == "spotlight-close":
        return False
    if isinstance(triggered, dict) and any(hits or []):
        return False
    raise PreventUpdate


@callback(
    Output("accordion", "active_item", allow_duplicate=True),
    Output("spotlight-selection", "data"),
    Input({"type": "spotlight-hit", "index": ALL}, "n_clicks"),
    State("spotlight-results", "children"),
    prevent_initial_call=True,
)
def spotlight_pick(hits, rendered):
    """Open the Explore section on the name that was clicked.

    The name is read back out of the rendered button rather than kept in a
    parallel list, so the label the user clicked and the name that is opened
    cannot disagree.
    """
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict) or not any(hits or []):
        raise PreventUpdate
    index = triggered["index"]
    try:
        chosen = rendered[index]["props"]["children"]
    except (TypeError, IndexError, KeyError):
        raise PreventUpdate
    return ACCORDION_SECTIONS[0][0], chosen


# The theme switch is clientside for two reasons: it must not wait on a server
# round trip to repaint, and the choice has to survive a reload, which means
# localStorage rather than Dash state. It sets data-theme on <html>; style.css
# defines the light palette against that attribute, so nothing else changes.
dash.clientside_callback(
    """
    function (n) {
        if (!n) { return window.dash_clientside.no_update; }
        var root = document.documentElement;
        var next = root.dataset.theme === 'light' ? 'dark' : 'light';
        root.dataset.theme = next;
        try { window.localStorage.setItem('ev-theme', next); } catch (e) {}
        // Nothing is written back into the button. Its icon is drawn by CSS
        // from data-theme, so there is no DOM for this callback to fight
        // with, which is what made the toggle need several clicks before.
        return window.dash_clientside.no_update;
    }
    """,
    Output("theme-toggle", "title"),
    Input("theme-toggle", "n_clicks"),
    prevent_initial_call=True,
)


# Scrolling is the other half of "bring it into scope": opening a section
# below the fold changes nothing the user can see. Dash cannot scroll, so this
# runs in the browser, after the section has had a moment to expand.
dash.clientside_callback(
    """
    function (compareClicks, trendsClicks, picked) {
        setTimeout(function () {
            var el = document.getElementById('accordion-anchor');
            if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }
        }, 250);
        return window.dash_clientside.no_update;
    }
    """,
    Output("spotlight-hotkey", "data"),
    Input("jump-compare", "n_clicks"),
    Input("jump-trends", "n_clicks"),
    Input("spotlight-selection", "data"),
    prevent_initial_call=True,
)


layout = dbc.Container(fluid = True, children = [
        offcanvas,
        spotlight,
        place_modal,
        dcc.Store(id="spotlight-hotkey"),
        dcc.Store(id="spotlight-selection"),
        # What the Explore tab should open on, when something else sends a
        # researcher there. Explore works out an author's available years
        # itself and lands on the earliest, which is right when a name is
        # typed into it and wrong when Top 10 hands it a researcher from a
        # particular edition. Read and cleared by auth_find.
        dcc.Store(id="explore-preset"),
        dede,
        html.Div(navigation_row),
        html.Br(),
        html.Hr(),
        dbc.Row(accordion),
        jump_sink,
        footer
        ], className = 'ev-page ev-shell')
