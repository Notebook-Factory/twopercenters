"""Top 10: who leads the selected edition, and which indicator puts them there.

The dashboard could say how one researcher compares, and how two compare, but
not who is at the top of the list it is built on. Every number needed to
answer that was already in the relational core.

There are two questions on this tab and they disagree with each other, which
is the point of putting them side by side. The composite score is the sum of
six log ratios, so two people can reach the same score by completely
different routes, and the six per-metric lists show it: in career-2024 the
third highest citation count for single-authored-or-first work belongs to
someone sitting at 7,167 on the published list.

Nothing here recomputes a published number. The stacked bar is the same
ln(v+1)/ln(max+1) term the Explore tab's bullet rows draw, so the segments
sum to the published score rather than to an approximation of it.
"""
import dash
import dash_bootstrap_components as dbc
import dash_daq as daq
import math
from dash import Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate

from citations_lib.auth_find import (WHATIF_METRICS, bullet_payload,
                                     bullet_rows, card_chips, card_header,
                                     rank_stats, register_bullet_chart)
from citations_lib.utils import (author_metrics, composite_is_reproducible,
                                 composite_maxima, edition_size,
                                 top_researchers, update_yr_options2)

SUFFIX = '_top10_'

# The six series colours, as CSS custom property names with the dark-mode
# value as a fallback. They are resolved in the browser at draw time, the way
# the bullet chart resolves its colours, so the charts follow a theme switch
# where a hex written into a figure could not.
#
# These are the chart series tokens rather than the interface accents: the
# six have to be told apart from each other, which is a stricter requirement
# than being visible against the page. See the comment on --ev-cat-1 in
# assets/style.css for what was checked.
SEGMENT_TOKENS = [
    ('--ev-cat-1', '#00A3CB'),
    ('--ev-cat-2', '#CE7D38'),
    ('--ev-cat-3', '#4FA866'),
    ('--ev-cat-4', '#9684DC'),
    ('--ev-cat-5', '#00ABA4'),
    ('--ev-cat-6', '#D8706F'),
]

def _values_for(author_id, kind, year, ns):
    """One researcher's six indicators, in the selected column set."""
    data = author_metrics(author_id, kind, year)
    if data is None:
        return None
    suffix = '_ns' if ns else ''
    return {metric: data.get(metric + suffix)
            for metric, _label in WHATIF_METRICS}


def composite_stack_payload(kind, year, ns=False):
    """The ten highest scores, each one taken apart into its six terms.

    A ranked list that prints only the score says who is on top and nothing
    about why. Every segment here is that indicator's own term in the score,
    ln(v+1)/ln(max+1), so the stack is the score rather than a picture of it,
    and the reader can see that the person at position three is there on
    citation volume while the one at position seven is there on
    single-authored work.

    career-2018 is the one edition whose published scores cannot be
    recomputed from its recorded maxima. The six terms are still each
    indicator's share of the edition maximum, so they are still drawn; what
    is not true of that edition is that they add up to the number printed
    beside them, and `reproducible` is how the layout knows to say so.
    """
    rows = top_researchers(kind, year, 'c', ns=ns)
    maxima = composite_maxima(kind, year, ns=ns)
    series = [{'key': metric, 'label': label, 'data': [],
               'values': [], 'token': SEGMENT_TOKENS[index][0],
               'fallback': SEGMENT_TOKENS[index][1]}
              for index, (metric, label) in enumerate(WHATIF_METRICS)]

    for row in rows:
        values = _values_for(row['author_id'], kind, year, ns) or {}
        for entry in series:
            value = values.get(entry['key'])
            ceiling = maxima.get(entry['key'])
            if value is None or not ceiling:
                entry['data'].append(0.0)
                entry['values'].append(None)
                continue
            share = (math.log(max(float(value), 0.0) + 1)
                     / math.log(ceiling + 1))
            # Eight places rather than six. Six rounds each segment by up
            # to 1e-6, and six of those accumulate to more than the sum is
            # allowed to drift from the published score it claims to be.
            entry['data'].append(round(share, 8))
            entry['values'].append(float(value))

    return {
        'positions': [row['position'] for row in rows],
        'names': [row['name'] for row in rows],
        'institutes': [row['institute'] for row in rows],
        'countries': [row['country_code'] for row in rows],
        'author_ids': [row['author_id'] for row in rows],
        'list_positions': [row['list_position'] for row in rows],
        'totals': [row['value'] for row in rows],
        'series': series,
        'reproducible': composite_is_reproducible(kind, year),
    }


def metric_grid_payload(kind, year, ns=False):
    """The top ten of each indicator, and who is also in the top ten overall.

    `shared` is the whole reason the six charts sit together. Drawn in the
    accent colour, the researchers who are also in the composite top ten pick
    themselves out, and the ones who lead an indicator without being anywhere
    near the top of the list stay muted. That contrast is the finding: being
    first in citations is not the same as being first.
    """
    best = {row['author_id'] for row in top_researchers(kind, year, 'c', ns=ns)}
    charts = []
    for metric, label in WHATIF_METRICS:
        rows = top_researchers(kind, year, metric, ns=ns)
        charts.append({
            'metric': metric,
            'label': label,
            'author_ids': [row['author_id'] for row in rows],
            'names': [row['name'] for row in rows],
            'institutes': [row['institute'] for row in rows],
            'values': [row['value'] for row in rows],
            'list_positions': [row['list_position'] for row in rows],
            'shared': [row['author_id'] in best for row in rows],
        })
    return {'charts': charts}


def card_children(author_id, kind, year, ns=False):
    """Everything the lean card shows for one researcher.

    Lean means no what-if inputs and no comparison group. Without a group
    there is no Elasticsearch aggregate to fetch, so a click on a name costs
    one Postgres row and the edition maxima, and the bars are drawn against
    the edition maximum alone.
    """
    data = author_metrics(author_id, kind, year)
    if data is None:
        return None
    suffix = '_ns' if ns else ''
    values = {metric: data.get(metric + suffix)
              for metric, _label in WHATIF_METRICS}
    rows = bullet_rows(values, composite_maxima(kind, year, ns=ns), {})

    edition = (f'Career to {year}' if kind == 'career'
               else f'Single year {year}')
    scopus_rank = data.get('rank' + suffix)
    list_rank = data.get('list_position' + suffix)
    subfield_rank = data.get('rank_subfield' + suffix)
    subfield_count = data.get('subfield_count')
    if subfield_rank and subfield_count:
        standing = (f'{int(subfield_rank):,} of {int(subfield_count):,} '
                    f'in {data["subfield"]}')
    else:
        # 2017 and 2018 carry no subfield rank at all, for every row. Saying
        # so beats printing the overall rank under a label promising a
        # different number, which is what the Explore card used to do.
        standing = 'Not recorded in this edition'

    return {
        'header': card_header(data['name'], data['institute'],
                              data['country_code'], data['field'], edition),
        'ranks': rank_stats(int(scopus_rank) if scopus_rank else None,
                            int(list_rank) if list_rank else None,
                            edition_size(kind, year)),
        'chips': card_chips(data.get('self_pct'), standing),
        'bullet': bullet_payload(rows, '', reference=False),
        'name': data['name'],
    }


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _toolbar():
    """The same three controls the Explore tab carries, and nothing else.

    The year radios are valued by the year itself rather than by an index
    into the option list, which is the form pages/home.py uses. An index is
    one indirection that only exists for historical reasons and it is the
    thing that makes a year picker point at the wrong year when an edition is
    added.
    """
    options, default = update_yr_options2(True)
    kind = html.Div([
        dbc.RadioItems(
            id='top10Kind' + SUFFIX,
            className='btn-group', inputClassName='btn-check',
            labelClassName='btn btn-outline-primary',
            labelCheckedClassName='active',
            value=True,
            options=[{'label': 'Career', 'value': True},
                     {'label': 'Single year', 'value': False}],
        )], className='radio-group')
    year = html.Div([
        dbc.RadioItems(
            id='top10Year' + SUFFIX,
            className='btn-group', inputClassName='btn-check',
            labelClassName='btn btn-outline-primary',
            labelCheckedClassName='active',
            value=default, options=options,
        )], className='radio-group year-picker')
    excluded = daq.BooleanSwitch(
        id='top10Ns' + SUFFIX, on=False,
        label='Exclude self-citations', labelPosition='bottom')
    return html.Div([
        html.Div([
            html.Div(kind, className='ev-picker-left'),
            html.Span(className='ev-picker-sep'),
            html.Div(year, className='ev-picker-right'),
        ], className='ev-picker'),
        html.Div(excluded, className='ev-top10-switch'),
    ], className='ev-toolbar ev-panel-toolbar')


def _card():
    """The card shell.

    Static for the same reason the Explore card's is: echarts attaches an
    instance to #top10CardBullet, and an element Dash replaces on every click
    is an element that instance no longer points at.
    """
    return html.Div([
        html.Div(id='top10CardHeader' + SUFFIX, className='ev-id-head'),
        html.Div(html.Div(id='top10CardRanks' + SUFFIX,
                          className='ev-id-ranks'),
                 className='ev-id-body'),
        html.Div(html.Div(id='top10CardBullet' + SUFFIX,
                          className='ev-bullet-chart'),
                 className='ev-bullets ev-bullets-lean'),
        dcc.Store(id='top10CardStore' + SUFFIX),
        html.Div(id='top10CardSink' + SUFFIX, style={'display': 'none'}),
        html.Div(id='top10CardChips' + SUFFIX, className='ev-id-chips'),
        html.Button([html.Span(className='ev-ic ev-ic-user'),
                     html.Span('Open in Explore')],
                    id='top10OpenExplore' + SUFFIX, n_clicks=0,
                    className='ev-share-btn ev-top10-open'),
    ], id='top10Card' + SUFFIX, className='ev-id-card ev-top10-card')


def _grid_cells():
    """Six chart divs, created once and never replaced.

    An element echarts has attached an instance to must not be replaced by a
    callback, which is the same rule the Explore card's chart divs follow.
    These six are fixed: there are six indicators, and which six does not
    depend on the selection.
    """
    cells = []
    for metric, label in WHATIF_METRICS:
        cells.append(html.Div([
            html.Div(label, className='ev-top10-cell-title'),
            html.Div(id=f'top10Cell{metric}' + SUFFIX,
                     className='ev-top10-cell-chart'),
        ], className='ev-top10-cell'))
    return cells


def top10_layout():
    """The whole tab. Holds no query: this is built once at import, and every
    number on it arrives through the callbacks below."""
    return html.Div([
        _toolbar(),
        html.Div([
            html.Div([
                html.Div([
                    html.H3('The ten highest composite scores',
                            className='ev-top10-title'),
                    html.P('Every bar is that researcher\'s score taken apart '
                           'into the six indicators that make it up. Click a '
                           'row to read the card beside it.',
                           className='ev-top10-sub'),
                ], className='ev-top10-head'),
                html.Div(id='top10CompositeNote' + SUFFIX,
                         className='ev-top10-note'),
                html.Div(id='top10Composite' + SUFFIX,
                         className='ev-top10-composite'),
                html.Div(id='top10Legend' + SUFFIX,
                         className='ev-top10-legend'),
            ], className='ev-top10-main'),
            html.Div(_card(), className='ev-top10-side'),
        ], className='ev-top10-row'),
        html.Div([
            html.Div([
                html.H3('The ten highest of each indicator',
                        className='ev-top10-title'),
                html.P('Coloured where the researcher is also in the top ten '
                       'overall, muted where leading one indicator is not '
                       'enough to get there. Hover a name to follow the same '
                       'person across all six.',
                       className='ev-top10-sub'),
            ], className='ev-top10-head'),
            html.Div(_grid_cells(), className='ev-top10-grid'),
        ], className='ev-top10-metrics'),
        dcc.Store(id='top10CompositeStore' + SUFFIX),
        dcc.Store(id='top10GridStore' + SUFFIX),
        # Which element each of the six indicators draws into, in the order
        # the grid payload lists them. The draw function is handed these
        # rather than building the ids itself, so the two cannot drift.
        dcc.Store(id='top10GridCells' + SUFFIX,
                  data=[f'top10Cell{metric}' + SUFFIX
                        for metric, _label in WHATIF_METRICS]),
        # How a click on a chart reaches the server.
        #
        # echarts fires its click event in the browser, and this Dash is 2.15,
        # which is before dash_clientside.set_props existed. So the draw
        # functions write the clicked author's id into this input the way a
        # user typing into it would, which is a change React and therefore
        # Dash both see. It is hidden because it is a channel, not a control.
        dcc.Input(id='top10Picked' + SUFFIX, value='', type='text',
                  style={'display': 'none'}),
        html.Div(id='top10CompositeSink' + SUFFIX, style={'display': 'none'}),
        html.Div(id='top10GridSink' + SUFFIX, style={'display': 'none'}),
    ], className='ev-top10')


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output('top10Year' + SUFFIX, 'options'),
    Output('top10Year' + SUFFIX, 'value'),
    Input('top10Kind' + SUFFIX, 'value'),
    State('top10Year' + SUFFIX, 'value'))
def _years(career, current):
    """The years this kind of edition has.

    The career series runs 2017 to 2024 and the single-year series has no
    2018, so switching kind can leave the picker pointing at a year that does
    not exist. Keeping the current year when it survives the switch means a
    reader comparing career-2022 with single-year-2022 does not have to
    reselect it every time.
    """
    options, default = update_yr_options2(career)
    available = {option['value'] for option in options
                 if not option.get('disabled')}
    return options, (current if current in available else default)


@callback(
    Output('top10CompositeStore' + SUFFIX, 'data'),
    Output('top10GridStore' + SUFFIX, 'data'),
    Output('top10CompositeNote' + SUFFIX, 'children'),
    Output('top10Legend' + SUFFIX, 'children'),
    Input('top10Kind' + SUFFIX, 'value'),
    Input('top10Year' + SUFFIX, 'value'),
    Input('top10Ns' + SUFFIX, 'on'))
def _charts(career, year, ns):
    kind = 'career' if career else 'singleyr'
    if not year:
        raise PreventUpdate
    composite = composite_stack_payload(kind, int(year), bool(ns))
    grid = metric_grid_payload(kind, int(year), bool(ns))

    note = []
    if not composite['reproducible']:
        note = html.Div(
            [html.Span(className='ev-ic ev-ic-triangle-alert'),
             html.Span('This edition\'s published scores cannot be '
                       'recomputed from the maxima recorded for it, so the '
                       'six parts below do not add up to the score beside '
                       'them. Every other edition reproduces exactly.')],
            className='ev-top10-warning')

    legend = [html.Span([html.Span(className='ev-top10-key',
                                   style={'background': entry['fallback']}),
                         html.Span(entry['label'])],
                        className='ev-legend-item')
              for entry in composite['series']]
    legend.append(html.Span(
        'each part is that indicator against the edition maximum, and the '
        'six add up to the published score',
        className='ev-legend-item ev-legend-note'))
    return composite, grid, note, legend


@callback(
    Output('top10CardHeader' + SUFFIX, 'children'),
    Output('top10CardRanks' + SUFFIX, 'children'),
    Output('top10CardChips' + SUFFIX, 'children'),
    Output('top10CardStore' + SUFFIX, 'data'),
    Input('top10Picked' + SUFFIX, 'value'),
    Input('top10Kind' + SUFFIX, 'value'),
    Input('top10Year' + SUFFIX, 'value'),
    Input('top10Ns' + SUFFIX, 'on'))
def _card_contents(picked, career, year, ns):
    """The card, for whoever was clicked.

    Falls back to the top of the list rather than to an empty card: nothing
    is clicked when the tab is first opened, and an empty card beside a
    populated list looks broken rather than expectant. It falls back the same
    way when the selection changes to an edition the clicked researcher is
    not in.
    """
    kind = 'career' if career else 'singleyr'
    if not year:
        raise PreventUpdate
    year = int(year)
    card = card_children(picked, kind, year, bool(ns)) if picked else None
    if card is None:
        leaders = top_researchers(kind, year, 'c', ns=bool(ns), limit=1)
        if not leaders:
            raise PreventUpdate
        card = card_children(leaders[0]['author_id'], kind, year, bool(ns))
    return card['header'], card['ranks'], card['chips'], card['bullet']


@callback(
    Output('accordion', 'active_item', allow_duplicate=True),
    Output('spotlight-selection', 'data', allow_duplicate=True),
    Input('top10OpenExplore' + SUFFIX, 'n_clicks'),
    State('top10CardHeader' + SUFFIX, 'children'),
    prevent_initial_call=True)
def _open_in_explore(clicks, header):
    """Hand this researcher to the Explore tab.

    The name is read back out of the rendered header rather than kept in a
    parallel store, which is how pages/home.py's spotlight does it: the name
    on screen and the name that gets opened cannot then disagree.
    """
    if not clicks:
        raise PreventUpdate
    try:
        name = header[0]['props']['children'][0]['props']['children']
    except (TypeError, IndexError, KeyError):
        raise PreventUpdate
    if not name or name == 'No author selected':
        raise PreventUpdate
    return 'explore', name


# ---------------------------------------------------------------------------
# The charts
# ---------------------------------------------------------------------------
#
# Drawn in the browser, for the same two reasons the bullet chart is: the
# colours are read from the CSS custom properties at draw time, so a theme
# switch is followed, and a click redraws without waiting for a figure to
# come back over the wire.
#
# The geometry constants here are shared with assets/style.css. COMPOSITE_ROW
# and the heights in .ev-top10-composite have to agree, and so do CELL_ROW and
# .ev-top10-cell-chart.

_PICK_JS = """
            // How a click gets to the server. See the comment on the hidden
            // input in top10_layout: React only notices a value it is told
            // about through its own setter, so setting .value directly does
            // nothing at all.
            function pick(authorId) {
                var input = document.getElementById('top10Picked%(suffix)s');
                if (!input || !authorId) { return; }
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(input, authorId);
                input.dispatchEvent(new Event('input', {bubbles: true}));
            }
""" % {'suffix': SUFFIX}

_COMMAS_JS = """
            function commas(v) {
                if (v === null || v === undefined) { return '-'; }
                var n = Math.round(v * 10) / 10;
                var whole = Math.floor(n);
                var s = whole.toLocaleString();
                return (n - whole) ? s + (n - whole).toFixed(1).slice(1) : s;
            }
"""

COMPOSITE_DRAW_JS = """
        function (payload, elementId) {
            var el = document.getElementById(elementId);
            if (!el || !window.echarts) { return ''; }

            function draw() {
            var chart = window.echarts.getInstanceByDom(el)
                        || window.echarts.init(el, null, {renderer: 'svg'});
            if (!payload || !payload.names || !payload.names.length) {
                chart.clear();
                return;
            }
            var ROW = 44, TOP = 12;
            var css = getComputedStyle(document.documentElement);
            function token(name, fallback) {
                var v = css.getPropertyValue(name);
                return (v && v.trim()) || fallback;
            }
            var text = token('--ev-text', '#E8ECF2');
            var muted = token('--ev-text-muted', '#A8B2C4');
            var accent = token('--ev-accent', '#00B4D8');
%(commas)s
%(pick)s
            var names = payload.names;
            var series = payload.series.map(function (entry, i) {
                return {
                    type: 'bar', stack: 'score', name: entry.label,
                    barWidth: 20,
                    // A 2px gap in the surface colour between segments.
                    // Two of the six separate by 6.0 under deuteranopia,
                    // which is inside the floor band where a second cue is
                    // required rather than optional; this is that cue, along
                    // with the legend and the per-segment hover.
                    itemStyle: {color: token(entry.token, entry.fallback),
                                borderColor: token('--ev-bg', '#394459'),
                                borderWidth: 2,
                                borderRadius: i === 0 ? [3, 0, 0, 3] : 0},
                    data: entry.data,
                    // The total at the end of the last segment, which is the
                    // published score. Printing it on the bar rather than in
                    // a column beside it keeps the number and the length it
                    // describes in one place.
                    label: i === payload.series.length - 1 ? {
                        show: true, position: 'right', color: text,
                        fontSize: 12, fontWeight: 600,
                        formatter: function (p) {
                            return payload.totals[p.dataIndex].toFixed(2); }
                    } : {show: false}
                };
            });

            chart.setOption({
                animationDuration: 260,
                grid: {left: 250, right: 62, top: TOP, bottom: 6,
                       height: names.length * ROW},
                tooltip: {
                    trigger: 'axis', axisPointer: {type: 'shadow'},
                    backgroundColor: '#303C54', borderColor: '#4A5670',
                    textStyle: {color: '#E8ECF2', fontSize: 12},
                    formatter: function (params) {
                        var list = [].concat(params);
                        var i = list.length ? list[0].dataIndex : -1;
                        if (i < 0) { return ''; }
                        var lines = ['<strong>' + names[i] + '</strong>',
                                     payload.institutes[i] || '',
                                     'score ' + payload.totals[i].toFixed(3)
                                     + ', position ' + payload.positions[i],
                                     ''];
                        payload.series.forEach(function (entry) {
                            lines.push(
                                entry.label + ': ' + commas(entry.values[i])
                                + '  (' + entry.data[i].toFixed(3) + ')');
                        });
                        return lines.join('<br/>');
                    }},
                xAxis: {
                    type: 'value', min: 0, max: 6, position: 'top',
                    // Six is where the score tops out: the six terms all at
                    // the edition maximum. Drawing every edition against the
                    // same 6 means bar lengths can be compared across the
                    // picker rather than only within one selection.
                    splitLine: {show: true, lineStyle: {opacity: 0.12}},
                    axisLine: {show: false}, axisTick: {show: false},
                    axisLabel: {color: muted, fontSize: 10}},
                yAxis: {
                    type: 'category', inverse: true, data: names,
                    axisLine: {show: false}, axisTick: {show: false},
                    axisLabel: {
                        formatter: function (value, index) {
                            var inst = payload.institutes[index] || '';
                            if (inst.length > 30) {
                                inst = inst.slice(0, 29) + '\\u2026';
                            }
                            var name = names[index];
                            if (name.length > 26) {
                                name = name.slice(0, 25) + '\\u2026';
                            }
                            return '{pos|' + payload.positions[index] + '}'
                                 + '{name|' + name + '}\\n'
                                 + '{inst|' + inst + '}';
                        },
                        rich: {
                            pos: {color: accent, fontSize: 13, fontWeight: 700,
                                  width: 26, align: 'left'},
                            name: {color: text, fontSize: 13, align: 'left'},
                            inst: {color: muted, fontSize: 10, align: 'left',
                                   padding: [2, 0, 0, 26]}}}},
                series: series
            }, true);
            chart.resize();

            chart.off('click');
            chart.on('click', function (params) {
                pick(payload.author_ids[params.dataIndex]);
            });
            }

            el.__evRedraw = draw;
            window.__evCharts = window.__evCharts || [];
            if (window.__evCharts.indexOf(el) < 0) {
                window.__evCharts.push(el);
                if (window.__evObserveSize) { window.__evObserveSize(el); }
            }
            draw();
            return '';
        }
""" % {'commas': _COMMAS_JS, 'pick': _PICK_JS}


GRID_DRAW_JS = """
        function (payload, cellIds) {
            if (!payload || !payload.charts || !window.echarts) { return ''; }

            function draw() {
            var css = getComputedStyle(document.documentElement);
            function token(name, fallback) {
                var v = css.getPropertyValue(name);
                return (v && v.trim()) || fallback;
            }
            var text = token('--ev-text', '#E8ECF2');
            var muted = token('--ev-text-muted', '#A8B2C4');
            var accent = token('--ev-accent', '#00B4D8');
            // Present but not pointed at. --ev-surface-2 measures 1.33:1
            // against the ground and simply vanishes; this is 3.17:1.
            var dim = token('--ev-cat-dim', '#8A93A6');
%(commas)s
%(pick)s
            // Every chart on the grid, so that hovering a name in one can
            // highlight the same researcher in the other five. Following one
            // person across six indicators is the question this grid exists
            // to answer, and without this it is six separate searches.
            var group = [];

            payload.charts.forEach(function (spec, index) {
                var el = document.getElementById(cellIds[index]);
                if (!el) { return; }
                var chart = window.echarts.getInstanceByDom(el)
                            || window.echarts.init(el, null,
                                                   {renderer: 'svg'});
                group.push({chart: chart, ids: spec.author_ids});

                chart.setOption({
                    animationDuration: 200,
                    grid: {left: 6, right: 58, top: 4, bottom: 4,
                           containLabel: true},
                    tooltip: {
                        trigger: 'item', backgroundColor: '#303C54',
                        borderColor: '#4A5670',
                        textStyle: {color: '#E8ECF2', fontSize: 12},
                        formatter: function (p) {
                            var i = p.dataIndex;
                            var place = spec.list_positions[i];
                            return '<strong>' + spec.names[i] + '</strong>'
                                 + '<br/>' + (spec.institutes[i] || '')
                                 + '<br/>' + spec.label + ': '
                                 + commas(spec.values[i])
                                 + '<br/>' + (place
                                    ? 'number ' + commas(place)
                                      + ' on the published list'
                                    : 'not placed on the published list');
                        }},
                    xAxis: {type: 'value', show: false,
                            max: Math.max.apply(null, spec.values) * 1.28},
                    yAxis: {
                        type: 'category', inverse: true,
                        data: spec.names.map(function (n) {
                            return n.length > 20 ? n.slice(0, 19) + '\\u2026'
                                                 : n; }),
                        axisLine: {show: false}, axisTick: {show: false},
                        axisLabel: {fontSize: 11,
                            color: function (value, index) {
                                return spec.shared[index] ? text : muted; }}},
                    series: [{
                        type: 'bar', barWidth: 11,
                        data: spec.values.map(function (v, i) {
                            return {value: v, itemStyle: {
                                color: spec.shared[i] ? accent : dim,
                                borderRadius: 2}}; }),
                        label: {show: true, position: 'right', fontSize: 10,
                                color: muted,
                                formatter: function (p) {
                                    return commas(p.value); }},
                        emphasis: {itemStyle: {color: accent}}
                    }]
                }, true);
                chart.resize();

                chart.off('click');
                chart.on('click', function (params) {
                    pick(spec.author_ids[params.dataIndex]);
                });
                chart.off('mouseover');
                chart.on('mouseover', function (params) {
                    var who = spec.author_ids[params.dataIndex];
                    group.forEach(function (other) {
                        var at = other.ids.indexOf(who);
                        if (at >= 0) {
                            other.chart.dispatchAction({
                                type: 'highlight', seriesIndex: 0,
                                dataIndex: at});
                        }
                    });
                });
                chart.off('mouseout');
                chart.on('mouseout', function () {
                    group.forEach(function (other) {
                        other.chart.dispatchAction({
                            type: 'downplay', seriesIndex: 0});
                    });
                });
            });
            }

            cellIds.forEach(function (id) {
                var el = document.getElementById(id);
                if (!el) { return; }
                el.__evRedraw = draw;
                window.__evCharts = window.__evCharts || [];
                if (window.__evCharts.indexOf(el) < 0) {
                    window.__evCharts.push(el);
                    if (window.__evObserveSize) { window.__evObserveSize(el); }
                }
            });
            draw();
            return '';
        }
""" % {'commas': _COMMAS_JS, 'pick': _PICK_JS}


dash.clientside_callback(
    COMPOSITE_DRAW_JS,
    Output('top10CompositeSink' + SUFFIX, 'children'),
    Input('top10CompositeStore' + SUFFIX, 'data'),
    State('top10Composite' + SUFFIX, 'id'))


dash.clientside_callback(
    GRID_DRAW_JS,
    Output('top10GridSink' + SUFFIX, 'children'),
    Input('top10GridStore' + SUFFIX, 'data'),
    State('top10GridCells' + SUFFIX, 'data'))
