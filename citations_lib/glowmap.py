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
from dash import Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate

from citations_lib.utils import (city_points, country_points,
                                 edition_years, update_yr_options2)

SUFFIX = '_glowmap_'

# The three questions the same rows can answer. `key` is the field in the
# payload; the label is what the control says.
MEASURES = (
    ('researchers', 'Researchers'),
    ('citations', 'Citations'),
    ('papers', 'Papers'),
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
        'country': [p['country_code'] for p in points],
        # Three decimals is about a hundred metres, which is finer than a
        # city, and saves a fifth of the payload.
        'lat': [round(p['lat'], 3) for p in points],
        'lng': [round(p['lng'], 3) for p in points],
        'researchers': [p['researchers'] for p in points],
        'citations': [p['citations'] for p in points],
        'papers': [p['papers'] for p in points],
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
    marks = {int(y): {'label': str(y)} for y in years}
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
        html.Div([
            html.Div([
                html.H3('Every city on the list', className='ev-glow-title'),
                html.P('One point per city, brighter where there is more of '
                       'the measure you pick. Points overlap and add up, so '
                       'a dense region reads as light rather than as dots. '
                       'Drag to pan, scroll to zoom.',
                       className='ev-glow-sub'),
            ]),
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
        html.Div(year_slider(), id='glowYearHolder' + SUFFIX,
                 className='ev-glow-years'),
        dcc.Store(id='glowMapStore' + SUFFIX),
        html.Div(id='glowMapSink' + SUFFIX, style={'display': 'none'}),
        html.Div(id='glowZoomSink' + SUFFIX, style={'display': 'none'}),
    ], className='ev-glow')


@callback(
    Output('glowMapStore' + SUFFIX, 'data'),
    Input('selectYrRadioHOME', 'value'),
    Input('careerORSingleYrRadioHOME', 'value'))
def _points(year, career):
    """Driven by the toolbar the choropleth above already has.

    Two pickers for two maps of the same selection would be two things to
    keep in agreement, and a reader would have to notice that they had
    drifted.
    """
    if year is None or career is None:
        raise PreventUpdate
    return map_payload('career' if career else 'singleyr', int(year))


@callback(
    Output('glowYearHolder' + SUFFIX, 'children'),
    Input('careerORSingleYrRadioHOME', 'value'),
    State('selectYrRadioHOME', 'value'))
def _rebuild_slider(career, year):
    """The track carries the years this kind of edition has.

    Career runs 2017 to 2024 and the single-year series has no 2018, so the
    marks are rebuilt rather than relabelled.
    """
    if career is None:
        raise PreventUpdate
    return year_slider(career, year)


@callback(
    Output('selectYrRadioHOME', 'value', allow_duplicate=True),
    Input('glowYear' + SUFFIX, 'value'),
    State('selectYrRadioHOME', 'value'),
    prevent_initial_call=True)
def _slider_sets_the_year(year, current):
    """Sliding moves the toolbar above, which is what everything else on the
    page reads. The guard is what stops the two from chasing each other:
    setting a value Dash already holds fires nothing further."""
    if year is None or str(year) == str(current):
        raise PreventUpdate
    return str(year)


@callback(
    Output('glowYear' + SUFFIX, 'value'),
    Input('selectYrRadioHOME', 'value'),
    State('glowYear' + SUFFIX, 'value'),
    prevent_initial_call=True)
def _the_year_moves_the_slider(year, current):
    """And the other way, so the buttons and the track never disagree."""
    if year is None or str(year) == str(current):
        raise PreventUpdate
    return int(year)


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
                               Math.pow(ratio, 2.2), i]);
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
                var LABELS = {researchers: 'on the list',
                              citations: 'citations', papers: 'papers'};

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
                var countryCeiling = Math.log(1 + countryLargest);
                var countryData = countries.map(function (c) {
                    // A gentler power than the lights use. The United States
                    // has 87,859 researchers and the median country has
                    // eleven, and a country is a large block of colour: the
                    // curve that reads well on a two-pixel point makes half
                    // the world look empty when it is a continent.
                    return {name: c.name,
                            value: Math.pow(
                                Math.log(1 + c[measure]) / countryCeiling,
                                1.4)};
                });
                var onCountries = grain === 'country';

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
                        map: 'world', roam: 'move', silent: true, z: 1,
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
                                        commas(c.papers) + ' papers'
                                       ].join('<br/>');
                            }
                            var i = p.value[3];
                            var lines = [
                                '<strong>' + payload.city[i] + ', '
                                + payload.country[i] + '</strong>',
                                commas(payload.researchers[i])
                                    + ' on the list',
                                commas(payload.citations[i]) + ' citations',
                                commas(payload.papers[i]) + ' papers'];
                            var named = payload.institutes[i] || [];
                            if (named.length) {
                                lines.push('');
                                lines.push(named.join('<br/>'));
                            }
                            return lines.join('<br/>');
                        }},
                    visualMap: {
                        // The mapped dimension is the log ratio above, so
                        // this runs 0 to 1 while the label reports the real
                        // largest value.
                        type: 'continuous', min: 0, max: 1,
                        // The third value in each point, which is the
                        // brightness. Without this echarts takes the last
                        // dimension, which here is the row index, so colour
                        // ran with a point's position in the array instead
                        // of with its value: London, the largest and the
                        // first row, came out the darkest colour on the
                        // scale. Density hid it at the whole-world view and
                        // it was obvious the moment the map was zoomed in.
                        // On the country reading the series is a map and
                        // each item carries one number, so the dimension to
                        // read is the first.
                        dimension: onCountries ? 0 : 2,
                        calculable: false,
                        // This bar is a legend, not a control. Left on,
                        // echarts' hoverLink highlights whatever sits in the
                        // range under the cursor, so running the mouse along
                        // the bar made the whole map flare at one end and do
                        // nothing anywhere else, which reads as a fault
                        // rather than as a feature.
                        hoverLink: false,
                        left: 12, bottom: 12, itemHeight: 110, itemWidth: 10,
                        // Explicit endpoint text. `showLabel` alone drew the
                        // gradient and no numbers at all, which is a scale
                        // that says nothing. The top of the bar names the
                        // measure as well as its largest value, so the
                        // legend reads without the control above it.
                        text: [commas(onCountries ? countryLargest : largest)
                               + ' ' + LABELS[measure], '0'],
                        textStyle: {color: muted, fontSize: 10},
                        // One hue, dark to light. The brightest places are
                        // near white because that is what the eye reads as
                        // intensity when points are adding up.
                        // The country reading starts from the land's own
                        // colour rather than from a dark amber, so a country
                        // with almost nobody sits a shade above the sea
                        // instead of reading as a filled-in value.
                        inRange: {color: onCountries
                            ? ['#1A2238', '#6B4A12', '#C98B1A', '#FFD48A',
                               '#FFF7E0']
                            : ['#6B4A12', '#C98B1A', '#FFD48A', '#FFF7E0']},
                        seriesIndex: 0,
                        formatter: function (value) { return commas(value); }
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
