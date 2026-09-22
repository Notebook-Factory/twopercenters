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
                var LABELS = {researchers: 'on the list',
                              citations: 'citations', papers: 'papers'};

                chart.setOption({
                    backgroundColor: GROUND,
                    geo: {
                        map: 'world', roam: true, silent: true,
                        // The land is a ground for the light to sit on, not
                        // a thing to read, so it carries no labels and no
                        // hover state of its own.
                        itemStyle: {areaColor: LAND, borderColor: BORDER,
                                    borderWidth: 0.5},
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
                        calculable: false,
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
                        data: data,
                        // Small and faint, not sized markers. A point per
                        // city at 17px reads as a pin dropped on a map; at
                        // 2 to 6px and a third of full opacity it reads as a
                        // light, and where cities crowd together the lights
                        // add up into the shape of a region. That
                        // accumulation is the picture, so the symbol has to
                        // stay small enough for it to happen.
                        symbolSize: function (value) {
                            return 1.4 + 4.6 * value[2];
                        },
                        itemStyle: {opacity: 0.38, borderWidth: 0},
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
            }

            // The outline is a megabyte, so it is fetched once per page and
            // every later draw waits on the same promise rather than
            // starting another download.
            if (!window.__evWorldMap) {
                window.__evWorldMap = fetch('/assets/world.geo.json')
                    .then(function (response) { return response.json(); })
                    .then(function (geo) {
                        window.echarts.registerMap('world', geo);
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


dash.clientside_callback(
    MAP_DRAW_JS,
    Output('glowMapSink' + SUFFIX, 'children'),
    Input('glowMapStore' + SUFFIX, 'data'),
    Input('glowMeasure' + SUFFIX, 'value'),
    State('glowMap' + SUFFIX, 'id'))
