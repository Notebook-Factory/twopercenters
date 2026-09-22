"""Where the work is, as light.

The choropleth above this fills each country with one colour, which answers
"which countries" and cannot answer "where". A country is not where anybody
works; an institution is, and since pipeline/ror_match.py matched those names
to the Research Organization Registry there are coordinates for them.

So this draws one point per city, and lets them overlap and add up. The
brightness of a place is the measure the reader picked, and dense regions
glow because the points are drawn with the screen's own additive blending
rather than painted over each other. That is the whole trick: `blendMode:
'lighter'`.

The points are the researchers whose institution could be located. That is
about seven in ten of them, and the rest are not on the map at all, which is
a property of free-text affiliation strings rather than of the dashboard.
"""
import dash
import dash_bootstrap_components as dbc
from dash import (Input, Output, State, callback, callback_context, dcc,
                  html)
from dash.exceptions import PreventUpdate

from citations_lib.utils import (city_points, country_points,
                                 edition_years, update_yr_options2)

SUFFIX = '_glowmap_'

# The three questions the same rows can answer. `key` is the field in the
# payload; the label is what the control says.
MEASURES = (
    ('researchers', 'Researcher count'),
    ('citations', 'Citations'),
    ('papers', 'Papers'),
    # The best h-index at a place, not the sum of them: adding h-indices
    # together produces a number that means nothing at all.
    ('h', 'Top h-index'),
)

# How coarsely to read the same edition. Cities are the located seven tenths
# of it; countries are all of it, because every fact row carries a country
# while only the matched ones carry coordinates.
GRAINS = (
    ('city', 'Cities'),
    ('country', 'Countries'),
)

# Two names per point. Four made the payload 513 KB and one made it 295 KB;
# two is 381 KB and still says what a city is known for when you hover it.
INSTITUTES_PER_POINT = 2


def map_payload(kind, year):
    """The map's data, as columns rather than as rows.

    A row per point repeats every key name 3,341 times. The same data in
    columns is 381 KB instead of 833 KB, and the chart wants columns anyway:
    it reads one array per axis.

    All three measures travel together. Switching between them is then a
    redraw in the browser rather than another round trip, which is right,
    because it is the same question asked of the same rows.
    """
    points = city_points(kind, year)
    return {
        # Every country in the edition, which is a short list and travels
        # with the long one so that changing granularity is a redraw rather
        # than another round trip.
        'countries': country_points(kind, year),
        'city': [p['city'] for p in points],
        'region': [p['region'] for p in points],
        'country': [p['country_code'] for p in points],
        # Three decimals is about a hundred metres, which is finer than a
        # city, and saves a fifth of the payload.
        'lat': [round(p['lat'], 3) for p in points],
        'lng': [round(p['lng'], 3) for p in points],
        'researchers': [p['researchers'] for p in points],
        'citations': [p['citations'] for p in points],
        'papers': [p['papers'] for p in points],
        'h': [p['h'] for p in points],
        'institutes': [p['institutes'][:INSTITUTES_PER_POINT] for p in points],
    }


def _segmented(component_id, options, value):
    """The button row this dashboard uses for every small choice."""
    return html.Div([
        dbc.RadioItems(
            id=component_id,
            className='btn-group', inputClassName='btn-check',
            labelClassName='btn btn-outline-primary',
            labelCheckedClassName='active',
            value=value,
            options=[{'label': label, 'value': key} for key, label in options],
        )], className='radio-group')


def year_slider(career=True, year=None):
    """The editions, as a track under the map.

    The radio buttons in the toolbar above say the same thing, and they stay:
    they are what the choropleth at the top of the page uses. This is for the
    map, where a reader wants to walk the years rather than aim at one, and
    the two are kept saying the same year in both directions.
    """
    years = edition_years('career' if career else 'singleyr')
    # Plain strings, not {'label': ...}. Both forms draw the same track, but
    # rc-slider's keyboard handler steps by looking the neighbouring mark up
    # in this dict and returning whatever it finds, so with the dict form a
    # left arrow set the slider's value to {'label': '2023'}. That is not a
    # number: the handle fell to the left end, the year read 2017, and the
    # next arrow press found nothing to step from and left it there.
    marks = {int(y): str(y) for y in years}
    chosen = int(year) if year else (years[-1] if years else 0)
    return dcc.Slider(
        id='glowYear' + SUFFIX,
        min=min(marks) if marks else 0, max=max(marks) if marks else 0,
        step=None, marks=marks, value=chosen,
        included=False, updatemode='mouseup',
        className='ev-glow-slider')


def glow_map():
    """The map, its controls, and the stores behind them."""
    measures = _segmented('glowMeasure' + SUFFIX, MEASURES, MEASURES[0][0])

    return html.Div([
        # One row of controls and no prose. What the map is showing is what
        # the buttons say, and a paragraph explaining that the points are
        # cities sat above a map of points on cities.
        html.Div([
            html.Div(id='glowKindHolder' + SUFFIX,
                     className='ev-glow-kind'),
            html.Div([
                _segmented('glowGrain' + SUFFIX, GRAINS, GRAINS[0][0]),
                measures,
            ], className='ev-glow-measures'),
        ], className='ev-glow-head'),
        html.Div([
            html.Div(id='glowMap' + SUFFIX, className='ev-glow-chart'),
            html.Div([
                html.Button('+', id='glowZoomIn' + SUFFIX, n_clicks=0,
                            title='Zoom in', className='ev-glow-zoom-btn'),
                html.Button('\u2212', id='glowZoomOut' + SUFFIX, n_clicks=0,
                            title='Zoom out', className='ev-glow-zoom-btn'),
                html.Button('\u21ba', id='glowZoomReset' + SUFFIX, n_clicks=0,
                            title='Whole world',
                            className='ev-glow-zoom-btn'),
            ], className='ev-glow-zoom'),
        ], className='ev-glow-frame'),
        html.Div([
            html.Button('\u2039', id='glowYearBack' + SUFFIX, n_clicks=0,
                        title='The edition before',
                        className='ev-glow-step'),
            html.Div(year_slider(), id='glowYearHolder' + SUFFIX,
                     className='ev-glow-years'),
            html.Button('\u203a', id='glowYearNext' + SUFFIX, n_clicks=0,
                        title='The edition after',
                        className='ev-glow-step'),
        ], className='ev-glow-track'),
        # How a click on the map reaches the server. This Dash is 2.15,
        # before dash_clientside.set_props, so the draw function writes into
        # this the way a person typing would and Dash sees a value change.
        # It carries 'country|USA' or 'city|London|GBR'.
        dcc.Input(id='glowPicked' + SUFFIX, value='', type='text',
                  style={'display': 'none'}),
        dcc.Store(id='glowMapStore' + SUFFIX),
        html.Div(id='glowMapSink' + SUFFIX, style={'display': 'none'}),
        html.Div(id='glowZoomSink' + SUFFIX, style={'display': 'none'}),
    ], className='ev-glow')


@callback(
    Output('glowMapStore' + SUFFIX, 'data'),
    Input('glowYear' + SUFFIX, 'value'),
    Input('careerORSingleYrRadioHOME', 'value'))
def _points(year, career):
    """The track under the map and the toggle above it, which are the only
    two controls the selection has."""
    if year is None or career is None:
        raise PreventUpdate
    return map_payload('career' if career else 'singleyr', int(year))


@callback(
    Output('glowYearHolder' + SUFFIX, 'children'),
    Input('careerORSingleYrRadioHOME', 'value'),
    State('glowYear' + SUFFIX, 'value'))
def _rebuild_slider(career, year):
    """The track carries the years this kind of edition has.

    Career runs 2017 to 2024 and the single-year series has no 2018, so the
    marks are rebuilt rather than relabelled.
    """
    if career is None:
        raise PreventUpdate
    return year_slider(career, year)


@callback(
    Output('glowYear' + SUFFIX, 'value', allow_duplicate=True),
    Input('glowYearBack' + SUFFIX, 'n_clicks'),
    Input('glowYearNext' + SUFFIX, 'n_clicks'),
    State('glowYear' + SUFFIX, 'value'),
    State('glowYear' + SUFFIX, 'marks'),
    prevent_initial_call=True)
def _step_a_year(back, forward, year, marks):
    """One edition at a time, from the arrows either side of the track.

    The editions are not consecutive in every series, since the single-year
    one has no 2018, so this steps along the marks that exist rather than
    adding one to the year.
    """
    if not marks or year is None:
        raise PreventUpdate
    years = sorted(int(mark) for mark in marks)
    try:
        at = years.index(int(year))
    except ValueError:
        raise PreventUpdate
    which = callback_context.triggered_id or ''
    step = -1 if str(which).startswith('glowYearBack') else 1
    moved = min(max(at + step, 0), len(years) - 1)
    if moved == at:
        # Already at one end. Returning the same value would be a no-op
        # anyway, but saying so keeps it out of the callback graph.
        raise PreventUpdate
    return years[moved]


# ---------------------------------------------------------------------------
# The drawing
# ---------------------------------------------------------------------------
#
# The world outline is a GeoJSON file in assets/, fetched the first time the
# map is drawn and registered with echarts once. ECharts 5 ships no maps at
# all, unlike 4, so this has to come from somewhere; it is served from this
# app rather than from a CDN so the page has one fewer third party in it, and
# it is fetched lazily because it is a megabyte and most readers never scroll
# this far.

MAP_DRAW_JS = """
        function (payload, measure, grain, elementId) {
            var el = document.getElementById(elementId);
            if (!el || !window.echarts) { return ''; }

            function draw() {
                var chart = window.echarts.getInstanceByDom(el)
                            || window.echarts.init(el, null,
                                                   {renderer: 'canvas'});
                if (!payload || !payload.lat || !payload.lat.length) {
                    chart.clear();
                    return;
                }
                // These are not theme tokens. A night-lights map is dark
                // in both themes for the same reason a photograph of a city
                // at night is: the subject is the light, and light needs
                // somewhere dark to be seen. A pale ground would leave the
                // faint places invisible and the bright ones grey.
                var LAND = '#141C2E';
                var BORDER = '#243049';
                var GROUND = '#0B1020';
                var muted = '#8894AC';

                var values = payload[measure] || payload.researchers;
                var largest = Math.max.apply(null, values);
                // Brightness runs with the logarithm of the value, not with
                // the value. London has 4,044 researchers and 54.6 million
                // citations; on a straight scale the citations view puts
                // almost every city at the dark end and the map goes blank
                // apart from a dozen places. The same log ratio the
                // composite score is built from keeps a city of 50,000
                // citations visible next to one of 50 million.
                var ceiling = Math.log(1 + largest);
                var data = [];
                for (var i = 0; i < values.length; i++) {
                    // The log ratio alone runs too hot: a city with fifty
                    // thousand citations is already three fifths of the way
                    // up a scale that ends at fifty million, so the map came
                    // back almost uniformly white. Raising it to a power
                    // puts the middle back down and leaves the bright places
                    // bright, which is how a city at night actually looks.
                    var ratio = Math.log(1 + values[i]) / ceiling;
                    data.push([payload.lng[i], payload.lat[i],
                               Math.pow(ratio, 2.2), i, values[i]]);
                }

                function commas(v) {
                    return (v === null || v === undefined)
                        ? '-' : Math.round(v).toLocaleString();
                }

                // A point is small and faint because at the whole-world view
                // its neighbours are on top of it and the light adds up.
                // Zoom in and they come apart, so the same point on its own
                // is a speck at a third of full opacity, which is close to
                // invisible: the map looked like it was fading out as you
                // went closer. Both size and opacity follow the zoom to keep
                // a place as bright when it is the only thing on screen.
                // Brightness does most of the compensating and size barely
                // moves. Growing both at the same rate turned the zoomed-in
                // map back into the sized markers this was drawn to get away
                // from: at eight times, points reached twenty pixels.
                function steps(zoom) {
                    return Math.log(Math.max(zoom, 1)) / Math.LN2;
                }
                function sizeAt(zoom) {
                    var spread = Math.min(1 + 0.25 * steps(zoom), 1.9);
                    return function (value) {
                        return (1.4 + 4.6 * value[2]) * spread;
                    };
                }
                function opacityAt(zoom) {
                    return Math.min(0.38 * (1 + 0.55 * steps(zoom)), 0.85);
                }
                // Twelve steps each, walked at even perceptual distance
                // through the anchors the two ramps have always had, so the
                // lightness climbs in equal amounts rather than crowding
                // four near-white swatches at the top. Warm for the city
                // lights, cool for the filled countries: a country should
                // never read as a lit city.
                var WARM = ['#6B4A12', '#7E5714', '#916416', '#A47218',
                            '#B87F19', '#CB8E22', '#D9A043', '#E6B25D',
                            '#F4C476', '#FFD690', '#FFE7B9', '#FFF7E0'];
                var COOL = ['#16233A', '#18364D', '#174B60', '#195F77',
                            '#1C748F', '#228AA6', '#2CA0BC', '#3EB7D1',
                            '#67CBE0', '#8AE0F0', '#BAEEF8', '#E8FBFF'];
                var LABELS = {researchers: 'researchers on the list',
                              citations: 'citations',
                              papers: 'papers',
                              h: 'best h-index'};

                // The legend, in real units.
                //
                // It used to be a gradient with "4,044 on the list" written
                // at one end, which says neither whose 4,044 nor that the
                // brightness between the ends runs on a log curve rather
                // than evenly. These are bands: each one says what a colour
                // actually means, and their widths are where the curve puts
                // them, so a reader can see that the top band is a tenth of
                // the range and most of the map is in the bottom one.
                // `power` is the same curve the reading it belongs to is
                // drawn with, so the bands fall where the colour actually
                // changes: 2.2 for the city lights, the gentler 1.4 for the
                // countries.
                function bands(largest, colours, power) {
                    var edges = [0];
                    var top = Math.log(1 + largest);
                    for (var b = 1; b < colours.length; b++) {
                        var at = Math.pow(b / colours.length, 1 / power);
                        var edge = Math.round(Math.exp(at * top) - 1);
                        // Where the range is short, two bands round to the
                        // same number and the one between them would be a
                        // swatch covering nothing at all. Top h-index is the
                        // case that bites: twelve bands over a range that
                        // ends at 293 has the bottom few landing on 5, 11,
                        // 19 and the ones below that all on 0.
                        if (edge > edges[edges.length - 1]) {
                            edges.push(edge);
                        }
                    }
                    var last = edges.length - 1;
                    var pieces = [];
                    for (var i = 0; i < edges.length; i++) {
                        var from = edges[i];
                        var to = (i + 1 < edges.length) ? edges[i + 1] : null;
                        // However many bands survive, the ramp runs from its
                        // darkest to its lightest across them, rather than
                        // stopping partway up because some were dropped.
                        var colour = colours[last
                            ? Math.round(i * (colours.length - 1) / last)
                            : colours.length - 1];
                        pieces.push(to === null
                            ? {gte: from, color: colour,
                               label: commas(from) + ' and over'}
                            : {gte: from, lt: to, color: colour,
                               label: commas(from) + ' to ' + commas(to)});
                    }
                    return pieces;
                }

                // The country reading of the same edition. Every fact row
                // carries a country and only the matched ones carry
                // coordinates, so this is the whole edition where the lights
                // are the seven tenths of it that could be placed.
                var countries = payload.countries || [];
                var byCountry = {};
                var countryValues = countries.map(function (c) {
                    byCountry[c.name] = c;
                    return c[measure];
                });
                var countryLargest = countryValues.length
                    ? Math.max.apply(null, countryValues) : 1;
                // The number a country carries is the count itself, in the
                // units the legend is written in. It used to carry a log
                // ratio between nought and one instead, which the bands,
                // being in researchers, read as nought: every country in
                // the world fell in the bottom band and the map came back
                // one flat colour. Where the bands sit is the gentler curve
                // now, and that is bands()' business, not the data's.
                var countryData = countries.map(function (c) {
                    return {name: c.name, value: c[measure]};
                });
                var onCountries = grain === 'country';
                // Worked out once rather than inside the option, because the
                // double-click handler below has to know which band it was
                // given: it identifies one by its colour, and every band in
                // both ramps has a colour of its own.
                var legendBands = onCountries
                    // A gentler curve than the lights use. The United States
                    // has 87,859 researchers and the median country has
                    // eleven, and a country is a large block of colour: the
                    // spacing that reads well on a two-pixel point leaves
                    // half the world in one band when it is a continent.
                    ? bands(countryLargest, COOL, 1.4)
                    : bands(largest, WARM, 2.2);

                function pick(what) {
                    var input = document.getElementById('glowPicked_glowmap_');
                    if (!input || !what) { return; }
                    var setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    // The same place twice running is a change Dash would
                    // not see, so a counter makes each click its own value.
                    window.__evPickCount = (window.__evPickCount || 0) + 1;
                    setter.call(input, what + '|' + window.__evPickCount);
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                }

                chart.setOption({
                    // No animation anywhere on this chart. Echarts animates
                    // an option update by default, so every restyle after a
                    // zoom was a third of a second of the points easing
                    // towards their new size while the map underneath had
                    // already arrived: the two looked out of step because
                    // they were.
                    animation: false,
                    backgroundColor: GROUND,
                    geo: [{
                        // Drag to pan, and the wheel is left alone.
                        //
                        // With roam true the wheel zooms the map, which
                        // means a reader scrolling the page stops dead here
                        // and the map dives to street level instead. The
                        // plotly map at the top of this page turned its
                        // scroll zoom off for exactly that reason, and this
                        // one repeated the mistake. Zooming is on the
                        // buttons in the corner.
                        // Not silent: on the country reading a click has
                        // to reach the region under the cursor.
                        map: 'world', roam: 'move', silent: false, z: 1,
                        // The land is a ground for the light to sit on, not
                        // a thing to read, so it carries no labels and no
                        // hover state of its own.
                        itemStyle: {areaColor: LAND, borderColor: BORDER,
                                    borderWidth: 0.5},
                        emphasis: {disabled: true},
                        // The view is deliberately not cropped to the
                        // inhabited latitudes. Doing that gave the map more
                        // room, and it also gave this component a different
                        // projection from the one the WebGL scatter
                        // assumes, so the points landed north and east of
                        // the land they belong to. One projection for both
                        // layers, and Antarctica stays.
                    }],
                    tooltip: {
                        trigger: 'item',
                        backgroundColor: '#303C54', borderColor: '#4A5670',
                        textStyle: {color: '#E8ECF2', fontSize: 12},
                        formatter: function (p) {
                            if (onCountries) {
                                var c = byCountry[p.name];
                                if (!c) { return ''; }
                                return ['<strong>' + c.name + '</strong>',
                                        commas(c.researchers) + ' on the list',
                                        commas(c.citations) + ' citations',
                                        commas(c.papers) + ' papers',
                                        'best h-index ' + commas(c.h)
                                       ].join('<br/>');
                            }
                            var i = p.value[3];
                            var lines = [
                                '<strong>' + payload.city[i]
                                + (payload.region[i]
                                   ? ', ' + payload.region[i] : '')
                                + ', ' + payload.country[i] + '</strong>',
                                commas(payload.researchers[i])
                                    + ' on the list',
                                commas(payload.citations[i]) + ' citations',
                                commas(payload.papers[i]) + ' papers',
                                'best h-index ' + commas(payload.h[i])];
                            var named = payload.institutes[i] || [];
                            if (named.length) {
                                lines.push('');
                                lines.push(named.join('<br/>'));
                            }
                            return lines.join('<br/>');
                        }},
                    visualMap: {
                        // Bands in real units rather than a gradient with
                        // one number written on it. See bands() above for
                        // why: a gradient cannot say that the brightness
                        // between its ends is a log curve, and a reader
                        // asked what "4,044 on the list" meant, which is a
                        // fair question of a legend.
                        type: 'piecewise',
                        // The raw value: the fifth number in each point on
                        // the city reading, and the only one there is on the
                        // country reading. Not the brightness, which is the
                        // log curve and means nothing to a reader.
                        dimension: onCountries ? 0 : 4,
                        pieces: legendBands,
                        // A legend, not a control: with hoverLink on,
                        // running the mouse along it made the map flare.
                        hoverLink: false,
                        // Explicitly on. Echarts turns the band labels off
                        // as soon as `text` is given, so naming the measure
                        // above the key silently took the numbers off it and
                        // left four coloured squares meaning nothing.
                        showLabel: true,
                        left: 12, bottom: 12,
                        itemWidth: 12, itemHeight: 9, itemGap: 2,
                        text: [LABELS[measure] +
                               (onCountries ? ', per country' : ', per city'),
                               'double-click a band for that band alone'],
                        textGap: 8,
                        textStyle: {color: muted, fontSize: 10},
                        seriesIndex: 0
                    },
                    series: [onCountries ? {
                        // The country reading fills the outline that is
                        // already there rather than drawing a second one:
                        // the series is bound to the geo above, so both
                        // readings pan and zoom as one thing.
                        type: 'map', geoIndex: 0, map: 'world',
                        data: countryData,
                        // Ten of the 174 countries in career-2024 have no
                        // feature in this outline at all, Taiwan, Hong Kong
                        // and Macau among them, which is 3,508 researchers
                        // that cannot be coloured. They keep their numbers
                        // everywhere else on the dashboard; it is this map
                        // file that has no shape for them.
                        select: {disabled: true}
                    } : {
                        type: 'scatter', coordinateSystem: 'geo',
                        geoIndex: 0, data: data, z: 5,
                        // Small and faint, not sized markers. A point per
                        // city at 17px reads as a pin dropped on a map; at
                        // 2 to 6px and a third of full opacity it reads as a
                        // light, and where cities crowd together the lights
                        // add up into the shape of a region. That
                        // accumulation is the picture, so the symbol has to
                        // stay small enough for it to happen.
                        symbolSize: sizeAt(1),
                        itemStyle: {opacity: opacityAt(1), borderWidth: 0},
                        // The whole effect. Overlapping points add their
                        // light together instead of the last one painted
                        // winning, which is why a dense region reads as a
                        // glow and not as a pile of dots.
                        blendMode: 'lighter',
                        // Every point painted in one pass, and chunked
                        // rendering explicitly refused.
                        //
                        // Echarts turns chunking on by itself above 3,000
                        // points, and this map has 3,341. Chunked, the
                        // display list holds 917 things: the 217 countries
                        // and one 700-point chunk. The other 2,641 points
                        // live in an incremental layer that a roam does not
                        // re-project, so dragging the map moved the land and
                        // left most of the lights where they were. Off, the
                        // list holds 3,558 things and every point moves with
                        // the map.
                        //
                        // It costs about 12 ms a frame. The speed it
                        // appeared to buy was partly an illusion anyway,
                        // since it was drawing a fifth of the points.
                        progressive: 0,
                        progressiveThreshold: 100000
                        // Echarts' large-scatter mode is deliberately not
                        // switched on here. It is the optimised path for
                        // tens of thousands of points, this map has 3,341,
                        // and rendered headlessly with it on every point
                        // vanished: the land drew and nothing else. Not
                        // worth the risk for a speed-up this size of data
                        // does not need.
                    }]
                }, true);
                chart.resize();

                // A click names a place. On the country reading that is the
                // region under the cursor; on the city reading it is the
                // point, which carries its row in the payload.
                chart.off('click');
                chart.on('click', function (params) {
                    if (onCountries) {
                        var c = byCountry[params.name];
                        if (c) { pick('country|' + c.country_code); }
                        return;
                    }
                    var i = params.value && params.value[3];
                    if (i === undefined || i === null) { return; }
                    // Where it is, not what it is called: there are
                    // Clevelands in Ohio and in Tennessee, and four Oxfords.
                    pick('city|' + payload.lat[i] + '|' + payload.lng[i]);
                });

                // Double-click a band to see only the places in it.
                //
                // A single click on a band already takes it out of the
                // picture, which is echarts' own behaviour and worth
                // keeping. The question a reader actually has is the other
                // way round: where are the cities in the top band on their
                // own, without the other eleven around them.
                //
                // This reads the two clicks rather than listening for a
                // dblclick on the canvas. A double click is two clicks, and
                // echarts rebuilds the key on each of them as the band goes
                // out and comes back, so by the time a dblclick arrives the
                // swatch under the cursor belongs to a key that has been
                // thrown away: its group has no parent, and there is nothing
                // left to say which band it was. What does survive is
                // echarts' own account of what changed, so the same band
                // going out and coming back inside 600ms is read as the
                // double click it was.
                var allOn = {};
                for (var band = 0; band < legendBands.length; band++) {
                    allOn[band] = true;
                }
                chart.__evSeen = allOn;
                chart.__evLastBand = -1;
                chart.__evLastAt = 0;
                chart.__evQuiet = false;
                chart.off('datarangeselected');
                chart.on('datarangeselected', function (params) {
                    var now = params.selected || {};
                    // Singling a band out is itself a selection change. It
                    // is not a reader's click and must not start a new pair.
                    if (chart.__evQuiet) { chart.__evQuiet = false; return; }
                    var shown = function (state, k) {
                        return state[k] !== false;
                    };
                    var before = chart.__evSeen || {};
                    var changed = -1, moved = 0;
                    for (var i = 0; i < legendBands.length; i++) {
                        if (shown(before, i) !== shown(now, i)) {
                            changed = i;
                            moved++;
                        }
                    }
                    var when = Date.now();
                    var twice = moved === 1
                        && changed === chart.__evLastBand
                        && when - chart.__evLastAt < 600;
                    var keep = {};
                    for (var c = 0; c < legendBands.length; c++) {
                        keep[c] = shown(now, c);
                    }
                    chart.__evSeen = keep;
                    chart.__evLastBand = changed;
                    chart.__evLastAt = when;
                    if (!twice) { return; }
                    var alone = shown(now, changed);
                    for (var k = 0; k < legendBands.length; k++) {
                        if (k !== changed && shown(now, k)) { alone = false; }
                    }
                    // Double-clicking the band that is already on its own
                    // puts the other eleven back, so the same gesture undoes
                    // itself and a reader is never stranded.
                    var selected = {};
                    for (var j = 0; j < legendBands.length; j++) {
                        selected[j] = alone ? true : (j === changed);
                    }
                    chart.__evSeen = selected;
                    chart.__evLastBand = -1;
                    chart.__evQuiet = true;
                    chart.dispatchAction({type: 'selectDataRange',
                                          selected: selected});
                });

                // Roaming fires continuously while the mouse is down, so the
                // restyle waits for a pause rather than running on every
                // frame of a drag.
                var pending = null, applied = 1;

                function settle() {
                    var view = ((chart.getOption().geo || [])[0] || {});
                    var zoom = view.zoom || 1;
                    if (Math.abs(zoom - applied) < 0.05) { return; }
                    applied = zoom;
                    chart.setOption({series: [{
                        symbolSize: sizeAt(zoom),
                        itemStyle: {opacity: opacityAt(zoom),
                                    borderWidth: 0}}]});
                }

                // Pinch to zoom, and only pinch.
                //
                // A trackpad pinch arrives as a wheel event with ctrlKey
                // set, which is how browsers have reported it since they
                // started supporting it; an ordinary wheel does not have it
                // and is left alone, so the page still scrolls past the map.
                // Touch screens send their own pinch through the same
                // handler below.
                if (!el.__evPinch && el.addEventListener) {
                    el.__evPinch = true;
                    el.addEventListener('wheel', function (event) {
                        if (!event.ctrlKey) { return; }
                        event.preventDefault();
                        var view = ((chart.getOption().geo || [])[0] || {});
                        var zoom = view.zoom || 1;
                        var factor = Math.exp(-event.deltaY / 120);
                        chart.setOption({geo: [{
                            zoom: Math.min(Math.max(zoom * factor, 1), 60)}]});
                        if (el.__evFollowZoom) { el.__evFollowZoom(); }
                    }, {passive: false});

                    var pinchFrom = null;
                    function spread(touches) {
                        var dx = touches[0].clientX - touches[1].clientX;
                        var dy = touches[0].clientY - touches[1].clientY;
                        return Math.sqrt(dx * dx + dy * dy);
                    }
                    el.addEventListener('touchstart', function (event) {
                        if (event.touches.length === 2) {
                            var view = ((chart.getOption().geo || [])[0] || {});
                            pinchFrom = {gap: spread(event.touches),
                                         zoom: view.zoom || 1};
                        }
                    }, {passive: true});
                    el.addEventListener('touchmove', function (event) {
                        if (event.touches.length !== 2 || !pinchFrom) { return; }
                        event.preventDefault();
                        var ratio = spread(event.touches) / pinchFrom.gap;
                        chart.setOption({geo: [{zoom: Math.min(
                            Math.max(pinchFrom.zoom * ratio, 1), 60)}]});
                    }, {passive: false});
                    el.addEventListener('touchend', function () {
                        pinchFrom = null;
                        if (el.__evFollowZoom) { el.__evFollowZoom(); }
                    }, {passive: true});
                }

                chart.off('georoam');
                chart.on('georoam', function () {
                    // Repaint now, every frame of the drag, not only when it
                    // settles. A series with a blend mode is composited on a
                    // canvas layer of its own, and a layer that nothing has
                    // marked dirty is put back where it was: the map slides
                    // and the points stay behind it.
                    var zr = chart.getZr();
                    if (zr) { zr.refresh(); }
                    if (pending) { clearTimeout(pending); }
                    pending = setTimeout(function () {
                        pending = null;
                        settle();
                    }, 90);
                });
                el.__evFollowZoom = settle;
            }

            // The outline is a megabyte, so it is fetched once per page and
            // every later draw waits on the same promise rather than
            // starting another download.
            if (!window.__evWorldMap) {
                window.__evWorldMap = fetch('/assets/world.geo.json')
                    .then(function (response) { return response.json(); })
                    .then(function (world) {
                        window.echarts.registerMap('world', world);
                        return true;
                    })
                    .catch(function () { return false; });
            }
            window.__evWorldMap.then(function (ready) {
                if (!ready) { return; }
                el.__evRedraw = draw;
                window.__evCharts = window.__evCharts || [];
                if (window.__evCharts.indexOf(el) < 0) {
                    window.__evCharts.push(el);
                    if (window.__evObserveSize) { window.__evObserveSize(el); }
                }
                draw();
            });
            return '';
        }
"""


# Zooming, on buttons rather than on the wheel. Written against the chart
# directly because it is one line of state that the server has no reason to
# hold: the view a reader has dragged to is theirs, and a round trip would
# make every press wait on it.
dash.clientside_callback(
    """
    function (zoomIn, zoomOut, reset, elementId) {
        var el = document.getElementById(elementId);
        var chart = el && window.echarts &&
                    window.echarts.getInstanceByDom(el);
        if (!chart) { return ''; }
        var trigger = (dash_clientside.callback_context.triggered || [])[0];
        if (!trigger || !trigger.value) { return ''; }
        var which = trigger.prop_id.split('.')[0];
        var view = ((chart.getOption().geo || [])[0] || {});
        var zoom = view.zoom || 1;
        if (which.indexOf('glowZoomIn') === 0) {
            zoom = Math.min(zoom * 1.6, 60);
        } else if (which.indexOf('glowZoomOut') === 0) {
            zoom = Math.max(zoom / 1.6, 1);
        } else {
            zoom = 1;
        }
        chart.setOption({geo: [{zoom: zoom,
                                center: zoom === 1 ? null : view.center}]});
        // The points are drawn for a zoom level, so they follow it here the
        // same way they follow a drag.
        if (el.__evFollowZoom) { el.__evFollowZoom(); }
        return '';
    }
    """,
    Output('glowZoomSink' + SUFFIX, 'children'),
    Input('glowZoomIn' + SUFFIX, 'n_clicks'),
    Input('glowZoomOut' + SUFFIX, 'n_clicks'),
    Input('glowZoomReset' + SUFFIX, 'n_clicks'),
    State('glowMap' + SUFFIX, 'id'),
    prevent_initial_call=True)


dash.clientside_callback(
    MAP_DRAW_JS,
    Output('glowMapSink' + SUFFIX, 'children'),
    Input('glowMapStore' + SUFFIX, 'data'),
    Input('glowMeasure' + SUFFIX, 'value'),
    Input('glowGrain' + SUFFIX, 'value'),
    State('glowMap' + SUFFIX, 'id'))
