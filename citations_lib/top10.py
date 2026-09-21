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
from dash import (ALL, Input, Output, State, callback, callback_context,
                  dcc, html)
from dash.exceptions import PreventUpdate

from citations_lib.auth_find import WHATIF_METRICS
from citations_lib.utils import (author_metrics, composite_is_reproducible,
                                 composite_maxima, top_researchers,
                                 update_yr_options2)

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
        'flags': [row['flag'] for row in rows],
        'author_ids': [row['author_id'] for row in rows],
        'list_positions': [row['list_position'] for row in rows],
        # A fraction in the fact table, a percentage everywhere a reader
        # sees it. The Explore card gets this figure from Elasticsearch,
        # where it is already scaled, which is why the two look like they
        # disagree if you read them side by side in the database.
        'self_pct': [None if row['self_pct'] is None else row['self_pct'] * 100
                     for row in rows],
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


def composite_rows(payload):
    """The ranked names, as buttons beside the chart.

    These are HTML rather than axis labels for two reasons. A two-line axis
    label cannot be aligned across rows, because echarts aligns each line
    inside the label box and the lines are different lengths. And a name a
    reader is meant to click should be a thing that can be clicked, focused
    and read by a screen reader, rather than text painted into an SVG.

    Row height here is the chart's ROW constant and the top padding is its
    TOP: see the comment above COMPOSITE_DRAW_JS. If one moves the other has
    to.
    """
    rows = []
    for index, name in enumerate(payload.get('names') or []):
        rows.append(html.Button(
            [html.Span(str(payload['positions'][index]),
                       className='ev-top10-rank'),
             _flag(payload['flags'][index], payload['countries'][index]),
             html.Span([
                 html.Span(name, className='ev-top10-name'),
                 html.Span(payload['institutes'][index] or '',
                           className='ev-top10-inst'),
                 _self_citation_bar(payload['self_pct'][index]),
             ], className='ev-top10-who')],
            id={'type': 'top10-row', 'index': name},
            n_clicks=0, className='ev-top10-listrow',
            title=f'Open {name} in Explore'))
    return rows


def _flag(code, country):
    """The country's flag, or its code when there is no flag to draw.

    The images come from flagfeed.com, which needs no key and serves circular
    PNGs keyed on the two-letter code. They are fetched by the reader's
    browser rather than by this server, and the alt text carries the country
    either way, so a reader who blocks the request, or who reads this after
    the service has gone, still knows which country it is.
    """
    if not code:
        return html.Span(country or '', className='ev-top10-flag-none')
    # dash-html-components 2.15 has no `loading` prop, so it goes through as
    # a data attribute rather than not at all.
    return html.Img(src=f'https://flagfeed.com/country/{code}',
                    alt=country or code.upper(), title=country or code.upper(),
                    className='ev-top10-flag', **{'data-loading': 'lazy'})


def _self_citation_bar(share):
    """What share of this researcher's citations are their own.

    The number on its own says nothing to a reader who has not seen the
    others, which is why the Explore card draws it as a bar too. The scale
    here is 30 percent rather than 100: almost everyone on these lists sits
    in the low single digits, and against 100 every one of them is the same
    invisible sliver. The number is printed beside the bar, so the scale
    cannot mislead about the value itself.
    """
    if share is None:
        return html.Span('', className='ev-top10-self')
    width = max(0.0, min(float(share) / 30.0 * 100.0, 100.0))
    return html.Span([
        html.Span(html.Span(className='ev-top10-self-fill',
                            style={'width': f'{width:.1f}%'}),
                  className='ev-top10-self-track'),
        # The number only. "self-cited" after every one of the ten was the
        # same two words ten times over, which is noise rather than a label;
        # the legend under the list says it once.
        html.Span(f'{share:.1f}%', className='ev-top10-self-value'),
    ], className='ev-top10-self',
        title=f'{share:.2f}% of the citations counted here are the '
              f"researcher's own")


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
                html.H3('The ten highest composite scores',
                        className='ev-top10-title'),
                html.P('Every bar is that researcher\'s score taken apart '
                       'into the six indicators that make it up. Click any '
                       'name to open them in Explore.',
                       className='ev-top10-sub'),
            ], className='ev-top10-head'),
            html.Div(id='top10CompositeNote' + SUFFIX,
                     className='ev-top10-note'),
            html.Div([
                html.Div(id='top10Rows' + SUFFIX,
                         className='ev-top10-rows'),
                html.Div(id='top10Composite' + SUFFIX,
                         className='ev-top10-composite'),
            ], className='ev-top10-listing'),
            html.Div(id='top10Legend' + SUFFIX,
                     className='ev-top10-legend'),
        ], className='ev-top10-main'),
        html.Div([
            html.Div([
                html.H3('The ten highest of each indicator',
                        className='ev-top10-title'),
                html.P('Who leads each of the six indicators that make up '
                       'the score. Hover a name to follow that person across '
                       'all six; click to open them in Explore.',
                       className='ev-top10-sub'),
                # What the two colours mean, next to the charts that use
                # them rather than in a sentence above them. Written out
                # because a reader who cannot tell why one bar is blue and
                # the next is grey reads the whole grid as random.
                html.Div([
                    html.Span([html.Span(className='ev-top10-key '
                                                   'ev-top10-key-shared'),
                               html.Span('also in the top ten overall')],
                              className='ev-legend-item'),
                    html.Span([html.Span(className='ev-top10-key '
                                                   'ev-top10-key-dim'),
                               html.Span('leads this indicator only')],
                              className='ev-legend-item'),
                    html.Span([html.Span(className='ev-top10-key '
                                                   'ev-top10-key-follow'),
                               html.Span('the one you are hovering')],
                              className='ev-legend-item'),
                ], className='ev-top10-legend'),
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
    Output('top10Rows' + SUFFIX, 'children'),
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
        [html.Span(className='ev-top10-key ev-top10-key-self'),
         html.Span('self-citations, under each name, against a scale that '
                   'ends at 30%')],
        className='ev-legend-item'))
    legend.append(html.Span(
        'each part is that indicator against the edition maximum, and the '
        'six add up to the published score',
        className='ev-legend-item ev-legend-note'))
    return composite, grid, composite_rows(composite), note, legend


@callback(
    Output('accordion', 'active_item', allow_duplicate=True),
    Output('spotlight-selection', 'data', allow_duplicate=True),
    Output('explore-preset', 'data', allow_duplicate=True),
    Input({'type': 'top10-row', 'index': ALL}, 'n_clicks'),
    Input('top10Picked' + SUFFIX, 'value'),
    State('top10Kind' + SUFFIX, 'value'),
    State('top10Year' + SUFFIX, 'value'),
    State('top10Ns' + SUFFIX, 'on'),
    prevent_initial_call=True)
def _open_in_explore(_row_clicks, picked, career, year, ns):
    """A click on any name opens that researcher in Explore.

    There is no card on this tab. One was built here first, and it repeated
    a smaller version of what Explore already draws properly, one click away,
    with the what-if calculator and the comparison group this tab has no room
    for. So a click goes there instead.

    Explore is keyed on the name, because that is what its Elasticsearch
    lookup takes and what its dropdown shows. Both ways in agree on it: the
    ranked rows carry it in the trigger and the small charts write it into
    the hidden input.

    The edition travels with the name. Explore would otherwise open on the
    earliest year that researcher appears in, which is a different question
    than the one being asked by clicking a name in the top ten of
    career-2024.
    """
    preset = {'career': bool(career), 'year': str(year or ''), 'ns': bool(ns)}
    trigger = callback_context.triggered_id
    fired = (callback_context.triggered or [{}])[0].get('value')
    if isinstance(trigger, dict) and trigger.get('type') == 'top10-row':
        # `fired` has to be checked, not just the trigger's shape. Changing
        # the picker replaces all ten rows, and Dash reports a newly rendered
        # row as the trigger with n_clicks of 0 or None. Without this, moving
        # the year would throw the reader into Explore.
        if not fired:
            raise PreventUpdate
        return 'explore', trigger['index'], preset
    if not picked:
        raise PreventUpdate
    return 'explore', picked, preset


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
            //
            // The name rather than the id, because Explore is keyed on the
            // name. Clicking the same person twice in a row is a no-op,
            // which is right: they are already open.
            function pick(name) {
                var input = document.getElementById('top10Picked%(suffix)s');
                if (!input || !name) { return; }
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(input, name);
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
            // TOP clears the axis labels, which sit above the plot: at 12
            // they were drawn half off the top of the element. ROW is the
            // height of one ranked row, which carries a name, an institution
            // and a self-citation bar, and is duplicated in
            // .ev-top10-listrow: see the comment there.
            var ROW = 52, TOP = 30;
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
                grid: {left: 6, right: 62, top: TOP, bottom: 6,
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
                    // The names live in HTML beside the chart. An axis label
                    // of two lines cannot be aligned reliably: echarts
                    // aligns each LINE inside the label box, so ten rows of
                    // different name lengths start at ten different offsets
                    // whichever way the label is aligned. The repo already
                    // solves this shape once, in the bullet chart, by
                    // putting the column of controls beside the chart and
                    // sharing the row geometry between the two.
                    axisLabel: {show: false}},
                series: series
            }, true);
            chart.resize();

            chart.off('click');
            chart.on('click', function (params) {
                pick(payload.names[params.dataIndex]);
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
            var follow = token('--ev-magenta', '#D86CB4');
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
                        // The names are events too, not only paint. Without
                        // this only the bar fires mouseover, so "hover a
                        // name" did nothing at all, and the name is the part
                        // a reader points at.
                        triggerEvent: true,
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
                        // Following someone is a third state, so it takes
                        // a third colour. Emphasising in the accent would
                        // have said "this one is in the top ten overall",
                        // which is what the accent already means here.
                        emphasis: {itemStyle: {color: follow}}
                    }]
                }, true);
                chart.resize();

                // Which row an event is about. A bar event carries its
                // dataIndex; an axis label event carries the label text and
                // no index, so the text is matched back against the
                // truncated names the axis was given.
                var shown = chart.getOption().yAxis[0].data;
                function rowOf(params) {
                    if (params.componentType === 'yAxis') {
                        return shown.indexOf(params.value);
                    }
                    return params.dataIndex === undefined
                        ? -1 : params.dataIndex;
                }
                function follows(at) {
                    if (at < 0) { return; }
                    var who = spec.author_ids[at];
                    group.forEach(function (other) {
                        var found = other.ids.indexOf(who);
                        if (found >= 0) {
                            other.chart.dispatchAction({
                                type: 'highlight', seriesIndex: 0,
                                dataIndex: found});
                        }
                    });
                }
                function clear() {
                    group.forEach(function (other) {
                        other.chart.dispatchAction({
                            type: 'downplay', seriesIndex: 0});
                    });
                }

                chart.off('click');
                chart.on('click', function (params) {
                    var at = rowOf(params);
                    if (at >= 0) { pick(spec.names[at]); }
                });
                chart.off('mouseover');
                chart.on('mouseover', function (params) {
                    follows(rowOf(params));
                });
                chart.off('mouseout');
                chart.on('mouseout', clear);
                // Leaving the chart altogether has to clear it too: mouseout
                // fires per element, and going from a bar straight off the
                // edge can leave the other five lit.
                chart.off('globalout');
                chart.on('globalout', clear);
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

