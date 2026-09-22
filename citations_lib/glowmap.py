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
                              citations: 'citations', papers: 'papers',
                              h: 'the best h-index'};

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
                                '<strong>' + payload.city[i] + ', '
                                + payload.country[i] + '</strong>',
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
                        // Two ramps, because the two readings are
                        // different kinds of picture. The lights are warm,
                        // the way a photograph of a city at night is. The
                        // countries are a cool single hue running from the
                        // land's own colour up through the dashboard's cyan
                        // to near-white, so a filled country never reads as
                        // a lit one and the two cannot be confused at a
                        // glance.
                        inRange: {color: onCountries
                            ? ['#16233A', '#164E63', '#1D7F9B', '#35B3CE',
                               '#8FE3F2', '#E8FBFF']
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
                    pick('city|' + payload.city[i] + '|'
                         + payload.country[i]);
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
