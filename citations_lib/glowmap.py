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

from citations_lib.utils import city_points

SUFFIX = '_glowmap_'

# The three questions the same rows can answer. `key` is the field in the
# payload; the label is what the control says.
MEASURES = (
    ('researchers', 'Researchers'),
    ('citations', 'Citations'),
    ('papers', 'Papers'),
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


def glow_map():
    """The map, its measure control, and the stores behind them."""
    measures = html.Div([
        dbc.RadioItems(
            id='glowMeasure' + SUFFIX,
            className='btn-group',
            inputClassName='btn-check',
            labelClassName='btn btn-outline-primary',
            labelCheckedClassName='active',
            value=MEASURES[0][0],
            options=[{'label': label, 'value': key}
                     for key, label in MEASURES],
        )], className='radio-group')

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
            html.Div(measures, className='ev-glow-measures'),
        ], className='ev-glow-head'),
        html.Div(id='glowMap' + SUFFIX, className='ev-glow-chart'),
        dcc.Store(id='glowMapStore' + SUFFIX),
        html.Div(id='glowMapSink' + SUFFIX, style={'display': 'none'}),
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
        function (payload, measure, elementId) {
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
                // The built-up area a city covers, a step above the land and
                // well below the lights. Invisible at the whole-world view,
                // which is right: it is there for when a reader zooms in and
                // wants to know whether a point sits on a city or on a field.
                var URBAN = '#1E2B45';
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

                chart.setOption({
                    // No animation anywhere on this chart. Echarts animates
                    // an option update by default, so every restyle after a
                    // zoom was a third of a second of the points easing
                    // towards their new size while the map underneath had
                    // already arrived: the two looked out of step because
                    // they were.
                    animation: false,
                    backgroundColor: GROUND,
                    geo: {
                        map: 'world', roam: true, silent: true,
                        // The land is a ground for the light to sit on, not
                        // a thing to read, so it carries no labels and no
                        // hover state of its own.
                        itemStyle: {areaColor: LAND, borderColor: BORDER,
                                    borderWidth: 0.5},
                        // The cities are one feature of the same map
                        // rather than a second layer, so they pan and zoom
                        // with the countries and there is no second viewport
                        // to keep in agreement.
                        //
                        // One feature, not 11,833. Drawn as separate shapes
                        // every zoom step took 210 ms, against 34 ms for the
                        // countries alone, and simplifying the outlines
                        // barely touched it: the cost is per shape, not per
                        // point. Collapsed into a single multi-polygon it is
                        // 69 ms, which is what the 2,143 largest cities cost
                        // before. They carry no hover and no identity, so
                        // there is nothing to lose by drawing them as one.
                        regions: [{name: 'urban-areas',
                                   itemStyle: {areaColor: URBAN,
                                               borderColor: URBAN,
                                               borderWidth: 0}}],
                        emphasis: {disabled: true},
                        // Antarctica is a third of the height and holds no
                        // researchers. Cutting the view off below the
                        // southern tip of the inhabited world gives the rest
                        // of the map the space instead.
                        boundingCoords: [[-180, 84], [180, -58]]
                    },
                    tooltip: {
                        trigger: 'item',
                        backgroundColor: '#303C54', borderColor: '#4A5670',
                        textStyle: {color: '#E8ECF2', fontSize: 12},
                        formatter: function (p) {
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
                        dimension: 2,
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
                        text: [commas(largest) + ' ' + LABELS[measure], '0'],
                        textStyle: {color: muted, fontSize: 10},
                        // One hue, dark to light. The brightest places are
                        // near white because that is what the eye reads as
                        // intensity when points are adding up.
                        inRange: {color: ['#6B4A12', '#C98B1A', '#FFD48A',
                                          '#FFF7E0']},
                        seriesIndex: 0,
                        formatter: function (value) { return commas(value); }
                    },
                    series: [{
                        type: 'scatter', coordinateSystem: 'geo',
                        data: data, z: 5,
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
                        // Painted in one pass rather than in chunks across
                        // frames. Echarts turns chunked rendering on by
                        // itself above 3,000 points and this map has 3,341,
                        // which puts it barely over a threshold meant for
                        // hundreds of thousands. One pass is both simpler
                        // and one less thing interacting with the additive
                        // blending above.
                        progressive: 0
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
                function follow() {
                    var current = ((chart.getOption().geo || [])[0] || {});
                    var zoom = current.zoom || 1;
                    if (Math.abs(zoom - applied) < 0.05) { return; }
                    applied = zoom;
                    chart.setOption({series: [{
                        symbolSize: sizeAt(zoom),
                        itemStyle: {opacity: opacityAt(zoom),
                                    borderWidth: 0}}]});
                }
                chart.off('georoam');
                chart.on('georoam', function () {
                    if (pending) { clearTimeout(pending); }
                    pending = setTimeout(function () {
                        pending = null;
                        follow();
                    }, 40);
                });
                el.__evFollowZoom = follow;
            }

            // The outline is a megabyte, so it is fetched once per page and
            // every later draw waits on the same promise rather than
            // starting another download.
            if (!window.__evWorldMap) {
                window.__evWorldMap = Promise.all([
                    fetch('/assets/world.geo.json').then(function (r) {
                        return r.json(); }),
                    // The cities are a separate file and a separate
                    // failure: if this one does not arrive the map still
                    // draws, with countries and lights and no footprints.
                    fetch('/assets/urban.geo.json').then(function (r) {
                        return r.json(); }).catch(function () { return null; })
                ]).then(function (both) {
                    var world = both[0];
                    var urban = both[1];
                    if (urban && urban.features) {
                        // Appended, so they draw over the countries rather
                        // than under them.
                        world = {type: 'FeatureCollection',
                                 features: world.features.concat(
                                     urban.features)};
                    }
                    window.echarts.registerMap('world', world);
                    return true;
                }).catch(function () { return false; });
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


dash.clientside_callback(
    MAP_DRAW_JS,
    Output('glowMapSink' + SUFFIX, 'children'),
    Input('glowMapStore' + SUFFIX, 'data'),
    Input('glowMeasure' + SUFFIX, 'value'),
    State('glowMap' + SUFFIX, 'id'))
