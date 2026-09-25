
# ==========================================================================================
# ==========================================================================================
# IMPORT LIBRARIES
# ==========================================================================================
# ==========================================================================================

# =============== misc libs & modules
import math
# =============== Plotly libs & modules
import country_converter as coco

# =============== Plotly Dash libraries
import dash
from dash import html, dcc, callback_context
from citations_lib.callbacks import callback, clientside_callback
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_daq as daq

# =============== Custom lib
from citations_lib.utils import (
    composite_is_reproducible, composite_maxima, composite_score,
    es_result_pick, get_es_aggregate, get_es_results, get_inst_field_cntry,
    openalex_author, score_standing)
from citations_lib.callback_templates import (
    generate_es_dropdown_callback, generate_update_cards_callback,
    generate_update_carsing_callback, generate_update_years_callback)
import dash_loading_spinners as dls
from citations_lib.controls import kind_toggle
# The what-if calculator.
#
# The composite score is not a black box: it is the sum of six log ratios,
# and citations_lib.utils.composite_score reproduces every published value
# exactly. So a reader can move any of the six indicators and be told,
# without a model and without a guess, where that score would have landed in
# the same edition.
#
# Everything the calculator draws is magenta, and everything published is
# cyan, on every bar and on the rank at once. A reader who looks away and
# back has to be able to tell in one glance whether the number in front of
# them is the researcher's or their own invention.
#
# Magenta rather than orange: the orange tick on each bar row already means
# the group median, and a what-if bar in the same colour would sit right on
# top of the thing it has to be told apart from.
GAUGE_BAR = '#00B4D8'
WHATIF_BAR = '#D86CB4'

# The six indicators, in the order the bullet rows are drawn, with the short
# label each input box carries as its tooltip.
WHATIF_METRICS = (
    ('nc', 'Citations'),
    ('h', 'H-index'),
    ('hm', 'Hm-index'),
    ('ncs', 'Cites, single-authored'),
    ('ncsf', 'Cites, single + first'),
    ('ncsfl', 'Cites, single + first + last'),
)


def bullet_rows(values, maxima, quartiles, composite_quartiles=None):
    """One row per indicator for the bullet chart in the author card.

    The six gauges this replaces each had their own axis -- 250k for
    citations, 200 for the h-index, 80 for hm -- so nothing could be compared
    across them and the group median landed as a 3px tick near zero on the
    wide ones.

    Every row here is that indicator's own term in the composite score,
    ln(v+1)/ln(max+1), which is between 0 and 1 for all six and sums to the
    published score. So one axis serves all of them, the median sits where it
    can be seen, and the parts visibly add up to the number the formula under
    the card produces.
    """
    rows = []
    for metric, label in WHATIF_METRICS:
        ceiling = maxima.get(metric)
        value = values.get(metric)
        if not ceiling or value is None:
            continue

        def share(x):
            return math.log(max(float(x), 0.0) + 1) / math.log(ceiling + 1)

        quarters = quartiles.get(metric) or {}

        def reference(x):
            # None rather than 0 when the group is absent. The Top 10 card
            # draws a researcher against the edition maximum and against no
            # group at all, and a 0 here is indistinguishable from a group
            # whose median really is 0: the chart would draw a tick hard
            # against the left edge and claim it meant something.
            return None if x is None else round(share(x), 4)

        rows.append({
            'key': metric,
            'label': label,
            'value': float(value),
            # The denominator, carried so the hover can print it. A bar that
            # reaches three quarters of the way across says nothing until the
            # reader knows what the far end is, and it is a different number
            # on every row and a different number in every edition.
            'ceiling': float(ceiling),
            'share': round(share(value), 4),
            'q1': reference(quarters.get('q1')),
            'median': reference(quarters.get('median')),
            'q3': reference(quarters.get('q3')),
            'median_raw': quarters.get('median'),
        })

    # The composite score as a seventh row.
    #
    # It belongs on the same axis as the six because it IS them: the score is
    # the sum of the six terms, so dividing by six puts it at their mean and
    # 1.0 keeps the meaning it has on every other row -- at the edition
    # ceiling on everything. The group's own quartiles for the score come from
    # the database rather than from summing the six medians, which would be
    # wrong: a median is not additive.
    if rows:
        total = sum(row['share'] for row in rows)
        quarters = composite_quartiles or {}

        def composite_share(x):
            return None if x is None else round(
                float(x) / len(WHATIF_METRICS), 4)

        rows.append({
            'key': 'c',
            'label': 'Composite score',
            'value': round(total, 4),
            # The score's own ceiling is the six terms all at 1, which is 6.
            'ceiling': float(len(WHATIF_METRICS)),
            'share': round(total / len(WHATIF_METRICS), 4),
            'q1': composite_share(quarters.get('q1')),
            'median': composite_share(quarters.get('median')),
            'q3': composite_share(quarters.get('q3')),
            'median_raw': quarters.get('median'),
            'composite': True,
        })
    return rows


def bullet_payload(rows, group_label, whatif=False, published=None,
                   reference=True, drag=None, suffix=''):
    """What the clientside bullet chart draws.

    `published` is the untouched set of rows, carried only in what-if mode so
    each bar can show where the real value sat before the reader moved it.

    `reference` is false for a card drawn without a comparison group, which
    is how the Top 10 tab draws one: no band, no median tick, just the bars
    against the edition maximum.

    `drag` is the id of the hidden input a dragged bar reports into. Only the
    what-if card passes one, and only then does the chart grow handles.
    `suffix` is that card's id suffix, so a drag can put its number straight
    into the box beside the row it is moving.
    """
    return {'rows': rows, 'group': str(group_label or ''),
            'whatif': bool(whatif),
            'reference': bool(reference),
            # The id of the hidden input a dragged bar reports into, or None
            # on a chart nobody can edit. The Top 10 card draws these same
            # rows and passes nothing, so it gets no handles.
            'drag': drag if whatif else None,
            'suffix': str(suffix),
            'published': published if whatif else None}


def comparison_legend(group_label):
    """What the comparison group does and does not set.

    This said "gauge maximum: the highest in <group>", which was true of the
    gauges and is true of nothing now. The bars divide by the EDITION maximum,
    the same denominator the published formula uses, which is why the six add
    up to the score and why a bar does not change length when the reader picks
    a different group to compare against.

    What the group sets is the two reference marks: the median and the middle
    half. The band was drawn from the first day and never named.
    """
    if not group_label:
        return []
    return [
        html.Span([html.Span(className='ev-legend-line'),
                   html.Span('median in '), html.Strong(str(group_label))],
                  className='ev-legend-item'),
        html.Span([html.Span(className='ev-legend-band'),
                   html.Span('middle half of '), html.Strong(str(group_label))],
                  className='ev-legend-item'),
        html.Span([html.Span('bar length is relative to the edition maximum, '
                             'as in the composite score')],
                  className='ev-legend-item ev-legend-note'),
    ]


def preset_choice(year_options, preset, career):
    """What to set when another tab hands this one a researcher.

    Returns (kind, year, exclude-self-citations, preset-to-keep), with
    dash.no_update for anything that must not move. Split out from the
    callback so the sequence can be tested: it takes two passes when the kind
    has to change, and getting that wrong either loops forever or silently
    leaves the reader on the wrong edition.
    """
    if not preset:
        raise PreventUpdate
    wanted_career = bool(preset.get('career'))
    if bool(career) != wanted_career:
        # The kind first. Changing it rebuilds the year options, and the
        # callback runs again on those, so the preset is kept for that pass.
        return wanted_career, dash.no_update, dash.no_update, preset
    wanted_year = str(preset.get('year') or '')
    available = {str(option['value']) for option in (year_options or [])
                 if not option.get('disabled')}
    # A researcher in the career-2024 top ten need not be in single-year
    # 2024, and an edition this author has no row in is not selectable. The
    # year Explore chose stands in that case, rather than a year that would
    # show nothing.
    year = wanted_year if wanted_year in available else dash.no_update
    return dash.no_update, year, bool(preset.get('ns')), None


# The what-if boxes, one per bullet row.
def box_value(metric, value):
    """What a box shows for one metric: the number, tidied for display.

    Hm is a fractional h-index and the only one of the six that is not a
    whole number. Everything else is a count, and a count in a box reading
    284984.0 looks like a bug.

    This is a display rounding and nothing else, which is why apply_whatif
    reads it too: a box still showing this is a box nobody has edited, and
    the score has to be recomputed from the researcher's real numbers rather
    than from the tidied ones. It was recomputed from the tidied ones, and
    turning what-if on with no edits moved 40 of 41 researchers around rank
    100,000, one of them by 174 places, on the strength of an hm of
    8.971429 being shown as 9.0.
    """
    if value is None:
        return None
    return round(float(value), 1) if metric == 'hm' else int(value)


def bullet_inputs(state, suffix='_author_find_'):
    """The six number boxes, aligned with the rows of the chart.

    They are the readout as well as the control: the value used to appear
    twice, once inside the gauge arc and again in a box underneath it.
    """
    cells = []
    for metric, label in WHATIF_METRICS:
        value = state['actual'].get(metric)
        # The h-index counts papers, so it cannot exceed the number of
        # papers. That ceiling is real and we know it, so the input
        # enforces it rather than letting someone claim an h-index of 900
        # from 120 papers. (It holds in the data too: h > np in 912 of
        # 1,402,942 published rows, so the cap is set above the published
        # value on the rare row where the publishers' own figure breaks
        # it.)
        maximum = None
        if metric == 'h' and state.get('np'):
            maximum = max(int(state['np']), int(value or 0))
        value = box_value(metric, value)
        # The tooltip goes on a wrapper: dbc.Input 1.3.1 rejects `title`
        # outright rather than passing it through to the <input>.
        cells.append(html.Div(
            dbc.Input(
                id = 'whatIf-' + metric + suffix, type = 'number',
                value = value, min = 0, max = maximum,
                step = 0.1 if metric == 'hm' else 1,
                # Commit on Enter or on leaving the box. With debounce off,
                # typing 90000 was five round trips, each one recomputing
                # the score and re-ranking against the whole edition.
                disabled = True, debounce = True,
                className = 'ev-whatif-input'),
            title = label + (f' (max {maximum:,})' if maximum else '')))

    # The composite box is a readout, not a control: the score is the sum
    # of the six above it, so it is never typed into. It is the fastest
    # thing on the card to watch while a what-if is being edited.
    total = composite_score(state['actual'], state['maxima'])
    cells.append(html.Div(
        dbc.Input(id = 'whatIf-c' + suffix, type = 'text',
                  value = '' if total is None else f'{total:.2f}',
                  disabled = True, readonly = True,
                  className = 'ev-whatif-input ev-whatif-derived'),
        title = 'Composite score, the sum of the six above'))

    # What the boxes are for once what-if is on. Opened by the what-if
    # callback, not by hovering, and closed on the first edit or after a few
    # seconds; hovering the box brings it back. Last in the column, so the
    # boxes above keep their places beside their rows.
    cells.append(dbc.Tooltip(
        [html.Strong('You can edit these now. '),
         'Drag a bar, or type a value into any box, to recompute the '
         'composite score and see where it would rank. The other numbers '
         'stay as published.'],
        # Above rather than to the left: to the left is the chart, and the
        # bars there are the other half of this instruction.
        id = 'whatIfTip' + suffix, target = 'whatIf-nc' + suffix,
        placement = 'top', is_open = False, trigger = 'hover',
        className = 'ev-whatif-tip'))
    return cells


def card_header(name, institute, country, field, edition=None):
    """Who this is, above the numbers, and which edition it is drawn from.

    The edition belongs here rather than under the numbers: every figure on
    the card is that edition's, and a reader who misses which year they are
    looking at misreads all of them.
    """
    def meta(icon, text):
        if not text or str(text).lower() in ('nan', 'none'):
            return None
        return html.Span([html.Span(className=f'ev-ic ev-ic-{icon}'),
                          html.Span(str(text))],
                         className='ev-id-meta-item')

    items = [meta('building-2', institute), meta('map-pin', country),
             meta('microscope', field)]
    left = html.Div([
        html.Div(name or 'No author selected', className='ev-id-name'),
        html.Div([i for i in items if i], className='ev-id-meta'),
    ])
    if not edition:
        return [left]
    return [left, html.Div([html.Span(className='ev-ic ev-ic-calendar'),
                            html.Span(edition)], className='ev-id-edition')]


def rank_stats(scopus_rank, list_rank, published, whatif=False, was=None):
    """The two ranks, side by side, with what each one counts.

    These used to be one number. `rank` is a position among every scientist
    Scopus scored, so on a list of 230,333 people it runs past a million, and
    printing it beside the size of the list produced statements that cannot
    be true. The position on the list is the number a reader assumed they
    were being shown, and it is the one that moves sensibly, so both are here
    and each is labelled with what it counts.
    """
    colour = WHATIF_BAR if whatif else GAUGE_BAR

    def cell(value, label, detail):
        return html.Div([
            html.Div(f'{value:,}' if isinstance(value, int) else '-',
                     className='ev-rank-value', style={'color': colour}),
            html.Div(label, className='ev-rank-label'),
            html.Div(detail, className='ev-rank-detail'),
        ], className='ev-rank-cell')

    if published and isinstance(list_rank, int) and list_rank > published:
        # A what-if score below everyone published is not on the list.
        list_cell = cell(None, 'off the list',
                         f'below all {published:,} published')
    else:
        list_cell = cell(list_rank, 'on this list',
                         f'of {published:,} published' if published else '')
    cells = [
        list_cell,
        cell(scopus_rank, 'Scopus rank', 'among everyone scored'),
    ]
    if whatif:
        cells.insert(0, html.Div([html.Span(className='ev-ic ev-ic-flask-conical'),
                                  html.Span('what if')],
                                 className='ev-id-badge'))
    children = [html.Div(cells, className='ev-rank-row')]
    if whatif and was:
        def number(value):
            return f'{value:,}' if isinstance(value, int) else '-'
        children.append(html.Div(
            [html.Span('published: '),
             html.Strong(number(was['list_rank'])), html.Span(' on this list, '),
             html.Strong(number(was['scopus_rank'])), html.Span(' Scopus')],
            className='ev-rank-was'))
    return children


def card_chips(self_pct, subfield_standing):
    """The two facts that are neither identity nor rank.

    Self-citation is a share, so it gets a bar rather than a number on its
    own: 10.59% means nothing to a reader who has not seen the others.
    """
    chips = []
    if self_pct is not None:
        share = max(0.0, min(float(self_pct), 100.0))
        chips.append(html.Div([
            html.Div([html.Span(className='ev-ic ev-ic-quote'),
                      html.Span('Self-citations'),
                      html.Strong(f'{share:.2f}%')], className='ev-chip-head'),
            html.Div(html.Div(className='ev-chip-fill',
                              style={'width': f'{share:.2f}%'}),
                     className='ev-chip-track'),
        ], className='ev-chip'))
    if subfield_standing:
        chips.append(html.Div([
            html.Div([html.Span(className='ev-ic ev-ic-target'),
                      html.Span('Subfield standing')], className='ev-chip-head'),
            html.Div(subfield_standing, className='ev-chip-body'),
        ], className='ev-chip'))
    return chips


def share_row(suffix):
    """Three ways to take the card somewhere else.

    The image is drawn from the figures rather than captured off the screen,
    so what gets shared cannot quietly disagree with what is on the page, and
    it always carries the published numbers: a what-if is an invention and
    has no business leaving the site looking like a record.
    """
    def button(name, icon, label):
        return html.Button(
            [html.Span(className=f'ev-ic ev-ic-{icon}'), html.Span(label)],
            id=name + suffix, n_clicks=0, className='ev-share-btn')

    return html.Div([
        button('shareX', 'share-2', 'Post on X'),
        button('shareImage', 'download', 'Download card'),
        button('shareCopy', 'clipboard-copy', 'Copy image'),
        html.Span(id='shareStatus' + suffix, className='ev-share-status'),
    ], className='ev-share-row')


def share_payload(name, institute, country, field, edition, standing,
                  self_pct, subfield_text):
    """Everything the share image prints. Published figures only."""
    if not standing:
        return None
    return {
        'name': name or '',
        'institute': str(institute or ''),
        'country': str(country or ''),
        'field': str(field or ''),
        'edition': edition or '',
        'list_rank': standing.get('within_list'),
        'scopus_rank': standing.get('scopus_rank'),
        'published': standing.get('published'),
        'self_pct': self_pct,
        'subfield': subfield_text or '',
    }


def rank_chart_payload(list_rank, scopus_rank, published, whatif=False):
    """What the clientside ECharts callback needs to draw the rank strip.

    The strip is the one picture that shows the whole point of the two
    numbers: the list runs from 1 to `published`, and a Scopus rank can sit
    far outside it. On a linear axis a rank of 60 and a rank of 908,824 put
    the interesting marker on the very edge, so the axis is logarithmic.
    """
    if not list_rank or not published:
        return None
    return {'list_rank': int(list_rank),
            'scopus_rank': int(scopus_rank) if scopus_rank else int(list_rank),
            'published': int(published),
            'whatif': bool(whatif)}


# The bullet rows.
#
# Drawn in the browser so a what-if keystroke redraws without waiting on a
# figure to come back over the wire, and so the colours can be read from
# the CSS custom properties at draw time, which means the chart follows a
# theme switch where the server-rendered plotly figures cannot.
#
# The geometry here is shared with assets/style.css: ROW and TOP set where
# each bar sits, and .ev-bullet-inputs positions its boxes to match. If one
# changes the other has to.
BULLET_DRAW_JS = """
        function (payload, elementId) {
            var el = document.getElementById(elementId);
            if (!el || !window.echarts) { return ''; }

            // Named so assets/charts.js can call it again when the theme
            // changes: the colours below are read from CSS at draw time, and
            // a chart already on screen does not redraw itself.
            function draw() {
            var chart = window.echarts.getInstanceByDom(el)
                        || window.echarts.init(el, null, {renderer: 'svg'});
            if (!payload || !payload.rows || !payload.rows.length) {
                chart.clear();
                return;
            }

            // TOP was 26 to clear the axis label across the top. There is
            // no axis label any more, so it is the gap under the card's
            // divider and nothing else.
            var ROW = 34, TOP = 10;
            var rows = payload.rows;
            var css = getComputedStyle(document.documentElement);
            function token(name, fallback) {
                var v = css.getPropertyValue(name);
                return (v && v.trim()) || fallback;
            }
            var accent = payload.whatif ? '#D86CB4'
                                        : token('--ev-accent', '#00B4D8');
            // The composite row keeps its own colour when published, because
            // it is a different kind of quantity from the six that make it
            // up. In what-if mode it goes magenta with everything else: the
            // distinction that matters there is invented against published,
            // and nothing hypothetical may be left looking published.
            var composite = payload.whatif ? '#D86CB4'
                                           : token('--ev-green', '#84B460');
            var orange = token('--ev-orange', '#F09048');
            var text = token('--ev-text', '#E8ECF2');
            // The track each bar runs in, and the group's middle half. They
            // were one colour, and --ev-surface-2 is a shade away from the
            // card it sits on, so the band could not be seen. The band is the
            // text colour, faintly: light on the dark theme, dark on the
            // light one, and off the track in both.
            var track = token('--ev-surface-2', '#4A5670');
            var band = token('--ev-text', '#E8ECF2');

            function commas(v) {
                var n = (Math.round(v * 10) / 10);
                var whole = Math.floor(n);
                var s = whole.toLocaleString();
                return (n - whole) ? s + (n - whole).toFixed(1).slice(1) : s;
            }

            // A card drawn without a comparison group has no band and no
            // median tick to draw. The Top 10 tab draws one: it shows a
            // researcher against the edition maximum, which is the same
            // denominator on every row, and against nobody else.
            var hasGroup = payload.reference !== false;

            var series = [];
            if (hasGroup) { series.push(
                // A band drawn from q1 rather than from zero says where most
                // of the group actually sits, which a gauge could not show at
                // all.
                // The group's middle half, drawn as a custom rect rather than
                // as a stacked bar. A stacked pair is its own bar group, and
                // echarts offsets bar groups within the category slot, so the
                // band sat half a row below the value it belongs to no matter
                // what barGap said. A custom series is positioned by hand
                // against the category centre, which is where the value bar
                // and the median tick already are.
                {type: 'custom', silent: true, z: 1,
                 renderItem: function (params, api) {
                     var row = api.value(0);
                     var a = api.coord([api.value(1), row]);
                     var b = api.coord([api.value(2), row]);
                     return {type: 'rect',
                             shape: {x: a[0], y: a[1] - 9,
                                     width: Math.max(b[0] - a[0], 1),
                                     height: 18},
                             style: {fill: band, opacity: 0.16}};
                 },
                 encode: {x: [1, 2], y: 0}, tooltip: {show: false},
                 data: rows.map(function (r, i) { return [i, r.q1, r.q3]; })});
            }
            series.push(
                // barGap -100% overlays this on the band instead of letting
                // echarts set it beside as a second bar group, which is what
                // put every value bar below the band it belongs to.
                // The bar sits in a track that runs the full width of the
                // axis, so the edition maximum is a visible edge every row
                // ends against. Without it a bar just stopped somewhere and
                // there was nothing to read its length against.
                {type: 'bar', barWidth: 8, barGap: '-100%', z: 3,
                 showBackground: true,
                 backgroundStyle: {color: track, opacity: 0.65,
                                   borderRadius: 2},
                 itemStyle: {color: accent, borderRadius: 2},
                 data: rows.map(function (r) {
                     return r.composite
                         ? {value: r.share, itemStyle: {color: composite}}
                         : r.share; }),
                 // This is the one series the row tooltip reads its index
                 // from, which is why the other three are excluded below.
                 });
            if (hasGroup) { series.push(
                {type: 'scatter', symbol: 'rect', symbolSize: [3, 22], z: 4,
                 itemStyle: {color: orange}, tooltip: {show: false},
                 data: rows.map(function (r, i) { return [r.median, i]; })});
            }
            if (payload.whatif && payload.published) {
                // Where the real value sat before it was moved.
                series.push({type: 'scatter', symbol: 'circle', symbolSize: 7,
                    z: 5, itemStyle: {color: 'transparent',
                                      borderColor: token('--ev-accent', '#00B4D8'),
                                      borderWidth: 2},
                    tooltip: {show: false},
                    data: payload.published.map(function (r, i) {
                        return [r.share, i]; })});
            }

            chart.setOption({
                animationDuration: 260,
                // 116px on the right is the input column, which is laid
                // out by CSS and sits over the chart. A card with no
                // comparison group has no inputs either, so that space is
                // the bars' to use.
                grid: {left: 150, right: hasGroup ? 116 : 30, top: TOP,
                       bottom: 8, height: rows.length * ROW},
                // One tooltip for the whole row, rather than one per series.
                //
                // It is triggered by the axis rather than by the item because
                // the thing worth hovering is the row, and several rows have
                // a bar a few pixels long: an h-index of 132 against a
                // ceiling of 328 is a wide bar, but single-authored citations
                // against 184,268 is not, and nobody should have to hit it.
                //
                // Everything about the row is in here, including the number
                // the bar is a share of. That number is the reason the axis
                // tick at the far end is gone: it read "edition max" on all
                // seven rows, which names the denominator without ever giving
                // one, and the denominators are seven different numbers that
                // change with the edition, the year and the self-citation
                // setting.
                tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'},
                          backgroundColor: '#303C54',
                          borderColor: '#4A5670',
                          textStyle: {color: '#E8ECF2', fontSize: 12},
                          formatter: function (params) {
                    var list = [].concat(params);
                    var i = list.length ? list[0].dataIndex : -1;
                    var r = rows[i];
                    if (!r) { return ''; }
                    // The score is a small number and commas() rounds to
                    // one decimal, which would print 5.2 beside a box reading
                    // 5.19. Its own row gets two.
                    function num(v) {
                        return r.composite ? Number(v).toFixed(2) : commas(v);
                    }
                    var lines = [
                        '<strong>' + r.label + '</strong>',
                        num(r.value) + ' of ' + num(r.ceiling)
                            + (r.composite
                               ? ', the six terms at their ceiling'
                               : ', the highest in this edition')];
                    if (r.median_raw !== null && r.median_raw !== undefined) {
                        lines.push('median in ' + payload.group + ': '
                                   + num(r.median_raw));
                    }
                    if (payload.whatif && payload.published
                        && payload.published[i]) {
                        lines.push('published: '
                                   + num(payload.published[i].value));
                    }
                    lines.push('contributes ' + r.share.toFixed(3)
                               + ' to the score');
                    return lines.join('<br/>');
                }},
                xAxis: {type: 'value', min: 0, max: 1, position: 'top',
                    axisLine: {show: false}, axisTick: {show: false},
                    axisLabel: {show: false},
                    splitLine: {show: false}},
                yAxis: {type: 'category', inverse: true,
                    data: rows.map(function (r) {
                        return r.composite ? {value: r.label, textStyle:
                            {color: composite, fontWeight: 600}} : r.label; }),
                    axisLine: {show: false}, axisTick: {show: false},
                    axisLabel: {color: text, fontSize: 12}},
                series: series
            }, true);
            chart.resize();

            // Drag a bar to change what it says.
            //
            // The bars are already the thing the calculator is about: each
            // one is that indicator's term in the composite score,
            // ln(v+1)/ln(ceiling+1), so its length IS what the row
            // contributes and dragging it is dragging the contribution. The
            // value that comes back out is the inverse of that,
            // exp(share * ln(ceiling+1)) - 1.
            //
            // Nothing goes to the server during a drag. The bar, the
            // composite row under it and the box beside it all move here,
            // and only when the handle is let go does the value go into the
            // hidden input that the card's recompute listens to. A drag is
            // one recompute, not one per pixel.
            //
            // The log axis makes the right-hand end coarse: on citations,
            // where the ceiling is in the millions, the pixels between 0.75
            // and 0.80 are 30,000 citations against 60,000. That is why the
            // boxes are still there, and the reason to type in them.
            var barIndex = hasGroup ? 1 : 0;
            var live = rows.map(function (r) { return r.share; });

            function valueAt(row, share) {
                return Math.exp(share * Math.log(row.ceiling + 1)) - 1;
            }

            // The score is the six terms added up, and its row is drawn at
            // their mean, so it follows a drag without asking anybody.
            function repaint() {
                var sum = 0;
                for (var k = 0; k < rows.length; k++) {
                    if (!rows[k].composite) { sum += live[k]; }
                }
                var six = rows.length - 1;
                var patch = [];
                for (var s = 0; s < barIndex; s++) { patch.push({}); }
                patch.push({data: rows.map(function (r, k) {
                    var share = r.composite ? (six ? sum / six : 0) : live[k];
                    return r.composite
                        ? {value: share, itemStyle: {color: composite}}
                        : share;
                })});
                chart.setOption({series: patch});
            }

            if (payload.drag && payload.rows.length) {
                var handles = [];
                for (var h = 0; h < rows.length; h++) {
                    if (rows[h].composite) { continue; }
                    handles.push(handleFor(h));
                }
                chart.setOption({graphic: handles});
            } else {
                chart.setOption({graphic: []});
            }

            function handleFor(index) {
                var row = rows[index];
                var at = chart.convertToPixel(
                    {xAxisIndex: 0, yAxisIndex: 0}, [live[index], index]);
                var left = chart.convertToPixel(
                    {xAxisIndex: 0, yAxisIndex: 0}, [0, index])[0];
                var right = chart.convertToPixel(
                    {xAxisIndex: 0, yAxisIndex: 0}, [1, index])[0];
                return {
                    type: 'circle', z: 100,
                    shape: {cx: 0, cy: 0, r: 7},
                    x: at[0], y: at[1],
                    style: {fill: accent, stroke: '#0B1020', lineWidth: 2},
                    cursor: 'ew-resize', draggable: 'horizontal',
                    ondrag: function () {
                        // Keep it on its own track. Dragged past either end
                        // the handle would leave the chart and the value
                        // would leave the scale with it.
                        this.x = Math.min(Math.max(this.x, left), right);
                        live[index] = (this.x - left) / (right - left);
                        rows[index].share = live[index];
                        rows[index].value = valueAt(row, live[index]);
                        repaint();
                        // The box beside the row, so the number and the bar
                        // never disagree while the mouse is down. Dash is
                        // told at the end of the drag, not now.
                        var box = document.getElementById(
                            'whatIf-' + row.key + payload.suffix);
                        if (box) {
                            box.value = row.key === 'hm'
                                ? rows[index].value.toFixed(1)
                                : String(Math.round(rows[index].value));
                        }
                        // And the score, which is those six terms added up.
                        var score = document.getElementById(
                            'whatIf-c' + payload.suffix);
                        if (score) {
                            var total = 0;
                            for (var t = 0; t < rows.length; t++) {
                                if (!rows[t].composite) { total += live[t]; }
                            }
                            score.value = total.toFixed(2);
                        }
                    },
                    ondragend: function () {
                        var value = valueAt(row, live[index]);
                        value = row.key === 'hm'
                            ? Math.round(value * 10) / 10
                            : Math.round(value);
                        var input = document.getElementById(payload.drag);
                        if (!input) { return; }
                        var setter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        // The same place twice running is a change Dash
                        // would not see, so a counter makes each drag its
                        // own value.
                        window.__evDragCount = (window.__evDragCount || 0) + 1;
                        setter.call(input, row.key + '|' + value + '|'
                                           + window.__evDragCount);
                        input.dispatchEvent(
                            new Event('input', {bubbles: true}));
                    }
                };
            }
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
        """


def register_bullet_chart(store_id, element_id, sink_id):
    """Draw one bullet store into one element.

    Two tabs draw these rows now, the Explore card and the Top 10 card, which
    is why the function above is a module-level constant rather than a string
    inside one tab's factory. The ids differ; the chart does not.
    """
    clientside_callback(
        BULLET_DRAW_JS,
        Output(sink_id, 'children'),
        Input(store_id, 'data'),
        State(element_id, 'id'))


def author_find_layout(default_author='Ioannidis, John P.A.'):
    """The "Find an author" tab.

    default_author lets the spotlight search open this tab on the name the
    user just picked. The tab's content is built on demand by home.py's
    switch_tab callback, so the dropdown does not exist until the tab is
    shown; seeding it at build time is what makes the hand-off work without
    a callback writing into a component that may not be mounted.
    """

    darkAccent1 = '#394459' # navy ground (Evidence)
    highlight1 = '#84B460' # green leaf
    SUFFIX = '_author_find_'

    careerORSingleA1 = kind_toggle("careerORSingleYrA1" + SUFFIX)

    selectYrA1 = html.Div(
        [dbc.RadioItems(
            id = "selectYrRadioA1" + SUFFIX, 
            className = "btn-group", 
            inputClassName = "btn-check", 
            labelClassName = "btn btn-outline-primary", 
            labelCheckedClassName = "active", 
            style = {'size':'sm'}, 
            value = '2017',
            options = [{"label": "2017", "value": "2017", 'disabled': False}]
        )
    ], className = "radio-group year-picker")

    # ========================================================================================== 
    # ========================================================================================== 
    # Row 2 Select authors!
    # ========================================================================================== 
    # ========================================================================================== 

    author1Options = dcc.Dropdown(options = [], placeholder = 'Search researchers', multi = False, id = "author1OptionsDropdown" + SUFFIX, 
        value = default_author, searchable = True)
    generate_es_dropdown_callback("author1OptionsDropdown" + SUFFIX)
    generate_update_carsing_callback('author1OptionsDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX)
    generate_update_years_callback('careerORSingleYrA1' + SUFFIX, 'selectYrRadioA1' + SUFFIX, 'author1OptionsDropdown' + SUFFIX)
    output_ids = ['InfoAuthor1' + SUFFIX, 'FieldAuthor1' + SUFFIX, 'CountryAuthor1' + SUFFIX, 'InstitutionAuthor1' + SUFFIX]
    generate_update_cards_callback('selectYrRadioA1' + SUFFIX, output_ids, 'author1OptionsDropdown' + SUFFIX, 'careerORSingleYrA1' + SUFFIX,darkAccent1, highlight1)

    # The group the reference marks describe. The label used to be the whole
    # sentence, three times over ("Max and median (red) by country"), which
    # said the line was red when it is orange and left no room for the thing
    # a reader actually picks. The sentence is a legend under the control now
    # and names the group, so the control is just the group.
    upper = html.Div([
        html.Span('Compare against', className='ev-control-label'),
        dcc.Dropdown(
            options=[{'label': 'Country', 'value': 'cntry'},
                     {'label': 'Field', 'value': 'sm-field'},
                     {'label': 'Institution', 'value': 'inst_name'}],
            multi=False, id="upper" + SUFFIX, value='cntry',
            clearable=False, searchable=False),
    ], className='ev-compare')

    row2 = dbc.Container([
        dbc.Row(dbc.Col(html.Div([
            html.Div(author1Options, className="ev-author-search"),
            html.Div([
                html.Div(careerORSingleA1, className="ev-picker-left"),
                html.Span(className="ev-picker-sep"),
                html.Div(selectYrA1, className="ev-picker-right"),
            ], className="ev-picker ev-picker-inline"),
        ], className="ev-explore-bar"), width = 12), justify='center'),
        dbc.Row([
            dbc.Col(html.Center(id = 'InfoAuthor1' + SUFFIX), width = {'size':8}, style={'visibility':'hidden','height':'0px'})
        ], justify ='center'), dbc.Row([
            dbc.Col(html.Center(id = 'FieldAuthor1' + SUFFIX), width = {'size':8}, style={'visibility':'hidden','height':'0px'})
        ], justify ='center'), dbc.Row([
            dbc.Col(html.Center(id = 'CountryAuthor1' + SUFFIX), width = {'size':8}, style={'visibility':'hidden','height':'0px'})
        ], justify ='center'), dbc.Row([
            dbc.Col(html.Center(id = 'InstitutionAuthor1' + SUFFIX), width = {'size':8}, style={'visibility':'hidden','height':'0px'})
        ], justify ='center')
    ])

    # ========================================================================================== 
    # ========================================================================================== 
    # Main Author Figure
    # ========================================================================================== 
    # ========================================================================================== 
    # =============== Toggle: % self-citations
    selfC = daq.BooleanSwitch(label = 'Exclude self-citations', labelPosition = 'bottom', id = 'selfCToggle' + SUFFIX)
    # =============== Toggle: the what-if calculator
    whatIf = daq.BooleanSwitch(label = 'What if', labelPosition = 'bottom',
                               id = 'whatIfToggle' + SUFFIX,
                               color = WHATIF_BAR)
    whatIfStore = dcc.Store(id = 'whatIfStore' + SUFFIX)
    # Closes the what-if tip a few seconds after it opens.
    whatIfTipTimer = dcc.Interval(id = 'whatIfTipTimer' + SUFFIX,
                                  interval = 8000, disabled = True)
    # =============== The author card
    #
    # Built as a shell here rather than inside the callback, because the
    # ECharts strip is drawn into #rankChart by a clientside callback and an
    # element Dash replaces on every author change is an element echarts has
    # already attached an instance to. The slots below are filled by
    # callbacks; the chart's own div is never destroyed.
    identityCard = html.Div([
        dcc.Store(id = 'rankChartStore' + SUFFIX),
        html.Div(id = 'cardHeader' + SUFFIX, className = 'ev-id-head'),
        # Filled by its own callback rather than as part of the header,
        # because resolving the researcher at OpenAlex is a call to somebody
        # else's server and takes about 600 ms the first time each name is
        # asked for. On the header's callback that would be 600 ms of blank
        # card; here the card draws at once and the link appears when it
        # arrives, or never, which is what happens when there is no
        # confident match.
        html.Div(id = 'openalexRow' + SUFFIX, className = 'ev-id-links'),
        html.Div([
            html.Div(id = 'rankDisplay' + SUFFIX, className = 'ev-id-ranks'),
            html.Div(id = 'rankChart' + SUFFIX, className = 'ev-rank-chart'),
        ], className = 'ev-id-body'),
        # The six indicators. The chart div is static for the same reason
        # #rankChart is: echarts attaches an instance to the element, and an
        # element Dash replaces on every author change is an element that
        # instance no longer points at. The input column beside it IS rebuilt
        # per author, because its values, caps and steps are the author's.
        html.Div([
            html.Div(id = 'bulletChart' + SUFFIX, className = 'ev-bullet-chart'),
            html.Div(id = 'bulletInputs' + SUFFIX,
                     className = 'ev-bullet-inputs'),
        ], className = 'ev-bullets'),
        dcc.Store(id = 'bulletStore' + SUFFIX),
        # How a dragged bar reaches the server: the chart writes
        # '<metric>|<value>|<counter>' in here the way a person typing
        # would, and the callback below puts the number in the box, which
        # recomputes the score exactly as typing it would have.
        dcc.Input(id = 'whatIfDrag' + SUFFIX, value = '', type = 'text',
                  style = {'display': 'none'}),
        html.Div(id = 'bulletSink' + SUFFIX, style = {'display': 'none'}),
        html.Div(id = 'cardChips' + SUFFIX, className = 'ev-id-chips'),
        share_row(SUFFIX),
        dcc.Store(id = 'shareStore' + SUFFIX),
        html.Div(id = 'rankChartSink' + SUFFIX, style = {'display': 'none'}),
    ], id = 'idCard' + SUFFIX, className = 'ev-id-card')

    # ECharts is loaded from the CDN (see app.py) and lives entirely in the
    # browser, so the figure is drawn from a small payload rather than
    # shipped as JSON. Colours are read off the CSS custom properties at draw
    # time, which is the one thing the server-rendered plotly charts on this
    # page cannot do: this strip follows a theme switch.
    clientside_callback(
        """
        function (payload, elementId) {
            var el = document.getElementById(elementId);
            if (!el || !window.echarts) { return ''; }

            // See the bullet chart above: named so a theme change can re-run
            // it, because the colours are read from CSS at draw time.
            function draw() {
            var chart = window.echarts.getInstanceByDom(el)
                        || window.echarts.init(el, null, {renderer: 'svg'});
            if (!payload) { chart.clear(); return; }

            var css = getComputedStyle(document.documentElement);
            function token(name, fallback) {
                var v = css.getPropertyValue(name);
                return (v && v.trim()) || fallback;
            }
            var muted = token('--ev-text-muted', '#A8B2C4');
            var accent = payload.whatif ? '#D86CB4' : token('--ev-accent', '#00B4D8');
            var orange = token('--ev-orange', '#F09048');
            var surface = token('--ev-surface-2', '#4A5670');

            function human(v) {
                if (v >= 1e6) { return (v / 1e6).toFixed(1) + 'M'; }
                if (v >= 1e3) { return Math.round(v / 1e3) + 'k'; }
                return String(v);
            }

            var ceiling = Math.max(payload.scopus_rank, payload.published);
            var span = ceiling * 1.15;
            // A label centred on a marker near either end of the axis runs
            // off the chart and is simply not drawn. A Scopus rank of
            // 908,824 on a list of 230,333 is exactly that case, and it is
            // the case the strip exists to show. So each label is anchored
            // away from whichever edge it is close to.
            function anchor(value) {
                var frac = Math.log(value) / Math.log(span);
                if (frac > 0.78) { return 'right'; }
                if (frac < 0.10) { return 'left'; }
                return 'center';
            }
            chart.setOption({
                animationDuration: 400,
                // The last axis tick sits at the maximum, so it needs room to
                // its right or it is drawn half off the chart.
                grid: {left: 6, right: 20, top: 32, bottom: 6, containLabel: true},
                xAxis: {
                    type: 'log', min: 1, max: span,
                    axisLine: {show: false}, axisTick: {show: false},
                    splitLine: {lineStyle: {color: surface, opacity: 0.35}},
                    axisLabel: {color: muted, fontSize: 10,
                                formatter: function (v) { return human(v); }}
                },
                yAxis: {type: 'value', min: 0, max: 1, show: false},
                series: [
                    {
                        // The extent of the published list, rank 1 to the
                        // last person on it. Everything outside this bar was
                        // scored but not published.
                        type: 'line', silent: true, symbol: 'none', z: 1,
                        data: [[1, 0.5], [payload.published, 0.5]],
                        lineStyle: {width: 12, color: surface, cap: 'round'}
                    },
                    {
                        type: 'line', silent: true, symbol: 'none', z: 2,
                        data: [[1, 0.5], [payload.list_rank, 0.5]],
                        lineStyle: {width: 12, color: accent, opacity: 0.35,
                                    cap: 'round'}
                    },
                    {
                        type: 'scatter', z: 4, symbolSize: 16,
                        data: [[payload.list_rank, 0.5]],
                        itemStyle: {color: accent, shadowBlur: 16,
                                    shadowColor: accent},
                        label: {
                            show: true, position: 'top', distance: 8,
                            align: anchor(payload.list_rank),
                            color: accent, fontWeight: 600, fontSize: 11,
                            formatter: function (p) {
                                return human(p.value[0]) + ' on this list';
                            }
                        }
                    },
                    {
                        type: 'scatter', z: 3, symbolSize: 11,
                        data: [[payload.scopus_rank, 0.5]],
                        itemStyle: {color: orange},
                        label: {
                            show: true, position: 'bottom', distance: 8,
                            align: anchor(payload.scopus_rank),
                            color: orange, fontSize: 11,
                            formatter: function (p) {
                                return 'Scopus ' + human(p.value[0]);
                            }
                        }
                    }
                ]
            }, true);
            chart.resize();
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
        """,
        Output('rankChartSink' + SUFFIX, 'children'),
        Input('rankChartStore' + SUFFIX, 'data'),
        State('rankChart' + SUFFIX, 'id'))

    # The share image is DRAWN, not captured.
    #
    # html2canvas and friends photograph the DOM, which here means a CSS mask
    # icon it cannot paint, a backdrop filter it cannot blur, and a strip
    # whose colours come from custom properties. Building the picture from
    # the same numbers the card shows avoids all of it, and the result is
    # sized for a social card rather than cropped from a page.
    #
    # It always prints the published figures. A what-if is an invention, and
    # an invention that leaves the site looking like a record is the one
    # outcome this whole page is built to prevent.
    clientside_callback(
        """
        function (nx, nimg, ncopy, share, strip) {
            var trig = (dash_clientside.callback_context.triggered || [])[0];
            if (!trig || !share || !window.echarts) { return ''; }
            var what = trig.prop_id.split('.')[0];
            if (!trig.value) { return ''; }

            var W = 1200, H = 630;
            var BG = '#303C54', CARD = '#394459', TEXT = '#E8ECF2';
            var MUTED = '#A8B2C4', ACCENT = '#00B4D8', ORANGE = '#F09048';

            function human(v) {
                if (v >= 1e6) { return (v / 1e6).toFixed(1) + 'M'; }
                if (v >= 1e3) { return Math.round(v / 1e3) + 'k'; }
                return String(v);
            }
            function commas(v) {
                return (v === null || v === undefined) ? '-'
                    : v.toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, ',');
            }

            var host = document.createElement('div');
            host.style.cssText = 'position:fixed;left:-99999px;top:0;width:'
                + W + 'px;height:' + H + 'px;';
            document.body.appendChild(host);
            var chart = window.echarts.init(host, null,
                {renderer: 'canvas', width: W, height: H});

            // `left` anchors an echarts graphic by its left edge, so a
            // right-aligned line still overflows the canvas and is cut off.
            // Anchoring from the right instead is what actually keeps it in.
            function text(x, y, str, size, colour, weight, fromRight) {
                var g = {type: 'text', top: y, silent: true,
                         style: {text: str, fontSize: size, fill: colour,
                                 fontWeight: weight || 'normal',
                                 fontFamily: 'system-ui, -apple-system, sans-serif'}};
                if (fromRight) { g.right = x; g.style.align = 'right'; }
                else { g.left = x; }
                return g;
            }

            var meta = [share.institute, share.country, share.field]
                       .filter(function (v) { return v; }).join('   ·   ');
            var graphics = [
                {type: 'rect', left: 0, top: 0, silent: true,
                 shape: {width: W, height: H}, style: {fill: BG}},
                {type: 'rect', left: 48, top: 44, silent: true,
                 shape: {width: W - 96, height: H - 88, r: 18},
                 style: {fill: CARD}},
                {type: 'rect', left: 48, top: 44, silent: true,
                 shape: {width: 6, height: H - 88}, style: {fill: ACCENT}},
                text(86, 86, share.name, 44, TEXT, 'bold'),
                text(86, 146, meta, 21, MUTED),
                text(86, 232, commas(share.list_rank), 76, ACCENT, 'bold'),
                text(86, 318, 'on this list', 22, TEXT, 'bold'),
                text(86, 348, 'of ' + commas(share.published) + ' published',
                     19, MUTED),
                text(430, 232, commas(share.scopus_rank), 76, ACCENT, 'bold'),
                text(430, 318, 'Scopus rank', 22, TEXT, 'bold'),
                text(430, 348, 'among everyone scored', 19, MUTED),
                text(86, H - 96, share.edition, 19, MUTED),
                text(86, H - 96, 'top 2% most-cited researchers', 19,
                     MUTED, 'normal', true)
            ];
            if (share.subfield) {
                graphics.push(text(750, 232, 'Subfield', 22, TEXT, 'bold'));
                graphics.push(text(750, 266, share.subfield, 19, MUTED));
            }
            if (share.self_pct !== null && share.self_pct !== undefined) {
                graphics.push(text(750, 318, 'Self-citations', 22, TEXT, 'bold'));
                graphics.push(text(750, 348, share.self_pct + '%', 19, MUTED));
            }

            var ceiling = Math.max(share.scopus_rank || 1, share.published || 1);
            chart.setOption({
                animation: false,
                graphic: graphics,
                grid: {left: 86, right: 86, top: H - 215, height: 56,
                       containLabel: false},
                xAxis: {
                    type: 'log', min: 1, max: ceiling * 1.15,
                    axisLine: {show: false}, axisTick: {show: false},
                    splitLine: {show: false},
                    axisLabel: {color: MUTED, fontSize: 14,
                                formatter: function (v) { return human(v); }}
                },
                yAxis: {type: 'value', min: 0, max: 1, show: false},
                series: [
                    {type: 'line', silent: true, symbol: 'none',
                     data: [[1, 0.6], [share.published, 0.6]],
                     lineStyle: {width: 14, color: '#4A5670', cap: 'round'}},
                    {type: 'line', silent: true, symbol: 'none',
                     data: [[1, 0.6], [share.list_rank, 0.6]],
                     lineStyle: {width: 14, color: ACCENT, opacity: 0.45,
                                 cap: 'round'}},
                    {type: 'scatter', symbolSize: 20, z: 4,
                     data: [[share.list_rank, 0.6]],
                     itemStyle: {color: ACCENT}},
                    {type: 'scatter', symbolSize: 14, z: 3,
                     data: [[share.scopus_rank, 0.6]],
                     itemStyle: {color: ORANGE}}
                ]
            }, true);

            var url = chart.getDataURL({type: 'png', pixelRatio: 2,
                                        backgroundColor: BG});
            chart.dispose();
            host.remove();

            var slug = (share.name || 'researcher').replace(/[^A-Za-z0-9]+/g, '-')
                       .replace(/^-|-$/g, '').toLowerCase();

            if (what.indexOf('shareX') === 0) {
                var line = share.name + ' ranks ' + commas(share.list_rank)
                    + ' of ' + commas(share.published) + ' on the top 2%'
                    + ' most-cited researchers list (' + share.edition + ').';
                window.open('https://twitter.com/intent/tweet?text='
                    + encodeURIComponent(line) + '&url='
                    + encodeURIComponent(window.location.origin), '_blank',
                    'noopener');
                return 'Opened X. Attach the downloaded card to the post.';
            }

            if (what.indexOf('shareImage') === 0) {
                var a = document.createElement('a');
                a.href = url;
                a.download = slug + '-' + (share.edition || 'card')
                             .replace(/[^A-Za-z0-9]+/g, '-') + '.png';
                document.body.appendChild(a);
                a.click();
                a.remove();
                return 'Card downloaded.';
            }

            if (what.indexOf('shareCopy') === 0) {
                if (!navigator.clipboard || !window.ClipboardItem) {
                    return 'This browser cannot copy images. Use Download.';
                }
                fetch(url).then(function (r) { return r.blob(); })
                  .then(function (blob) {
                    return navigator.clipboard.write(
                        [new ClipboardItem({'image/png': blob})]);
                  }).catch(function () {});
                return 'Card copied to the clipboard.';
            }
            return '';
        }
        """,
        Output('shareStatus' + SUFFIX, 'children'),
        Input('shareX' + SUFFIX, 'n_clicks'),
        Input('shareImage' + SUFFIX, 'n_clicks'),
        Input('shareCopy' + SUFFIX, 'n_clicks'),
        State('shareStore' + SUFFIX, 'data'),
        State('rankChartStore' + SUFFIX, 'data'),
        prevent_initial_call=True)

    register_bullet_chart('bulletStore' + SUFFIX,
                          'bulletChart' + SUFFIX,
                          'bulletSink' + SUFFIX)

    @callback(
        Output('openalexRow' + SUFFIX, 'children'),
        Input('author1OptionsDropdown' + SUFFIX, 'value'))
    def _openalex_link(name):
        """Where to read the work behind the numbers.

        This dashboard reports what the published list says and stops there.
        A reader who wants the papers has only the name to go on, and
        OpenAlex is where that name resolves to a profile.

        No link is shown unless OpenAlex returns a researcher whose name
        matches this one once punctuation, case, order and initials are set
        aside. A search for a common surname returns the most cited match
        rather than the right one, and a link to the wrong researcher is a
        claim this dashboard has no business making.
        """
        url = openalex_author(name) if name else None
        if not url:
            return []
        return html.A([html.Span(className='ev-ic ev-ic-external-link'),
                       html.Span('Open in OpenAlex')],
                      href=url, target='_blank', rel='noopener noreferrer',
                      className='ev-id-link')

    @callback(
        Output('careerORSingleYrA1' + SUFFIX, 'value', allow_duplicate=True),
        Output('selectYrRadioA1' + SUFFIX, 'value', allow_duplicate=True),
        Output('selfCToggle' + SUFFIX, 'on', allow_duplicate=True),
        Output('explore-preset', 'data', allow_duplicate=True),
        Input('selectYrRadioA1' + SUFFIX, 'options'),
        State('explore-preset', 'data'),
        State('careerORSingleYrA1' + SUFFIX, 'value'),
        prevent_initial_call=True)
    def _apply_preset(year_options, preset, career):
        """Open on the edition the reader was already looking at.

        Explore works out which years an author has and lands on the earliest
        one, which is what somebody typing a name wants: it is the start of
        that researcher's record. It is not what somebody arriving from the
        Top 10 of career-2024 wants, and landing them on 2017 silently
        answers a different question than the one they clicked on.

        This runs off the year options rather than off the store, because the
        options are the last thing to arrive: the author sets the kind, the
        kind sets the years, and only then is there a 2024 to select. Setting
        the kind here sends the years round again, so the preset is kept
        until the year is actually applied and cleared once it is. Without
        that it would run forever, and with a preset that is never cleared
        the reader could not change the year by hand afterwards.
        """
        return preset_choice(year_options, preset, career)

    # =============== The card, across the row
    #
    # It shared this row with a plotly gauge of the composite score. The score
    # is the seventh bullet row now, which is where it belongs -- beside the
    # six terms it is the sum of -- so the card has the width to itself.
    metricsFigAuthor_c = dbc.Row(dbc.Col(identityCard, width = 12))
    def _whatif_note(state):
        if not state['reproducible']:
            return html.Div(
                'The what-if calculator is off for this edition. Its '
                'published scores cannot be rebuilt from the recorded maxima, '
                'so a score computed here would not match the one shown '
                'above.',
                className = 'ev-whatif-note')
        # Where the calculator works there is nothing to say here: switching
        # it on opens a tip on the boxes themselves (whatif_tip).
        return None

    # =============== Figure callbacks
    @callback(
        Output('2author_figs' + SUFFIX, 'children'), 
        Output('whatIfStore' + SUFFIX, 'data'),
        Output('whatIfToggle' + SUFFIX, 'on'),
        Output('cardHeader' + SUFFIX, 'children'),
        Output('cardChips' + SUFFIX, 'children'),
        Output('rankDisplay' + SUFFIX, 'children'),
        Output('rankChartStore' + SUFFIX, 'data'),
        Output('idCard' + SUFFIX, 'className'),
        Output('shareStore' + SUFFIX, 'data'),
        Output('comparisonLegend' + SUFFIX, 'children'),
        Output('bulletStore' + SUFFIX, 'data'),
        Output('bulletInputs' + SUFFIX, 'children'),
        [Input('careerORSingleYrA1' + SUFFIX, 'value'),
        Input('selectYrRadioA1' + SUFFIX,'value'),
        Input('selfCToggle' + SUFFIX, 'on'), 
        Input('author1OptionsDropdown' + SUFFIX, 'value'), 
        Input("upper" + SUFFIX,'value')], 
        )
    def update_author_figso_and_rank(career1, yr1, ns, group1_name,uplim):
        '''
        group1_name: author name
        '''
        # One value per output, in the order the decorator lists them: the
        # empty card, for when there is no author to draw. This used to carry
        # a fourteenth value (a leftover empty figure) that shifted every
        # value after it one output along, so Dash rejected the whole return.
        no_author = (["No dataset selected"], None, False,
                     card_header(None, None, None, None), [], [], None,
                     'ev-id-card', None, [], None, [])
        if career1 == None or yr1 == None: raise PreventUpdate
        elif group1_name == None:
            return no_author
        else:
            prefix1 = 'career' if career1 else 'singleyr'
            # exact=True: the author name comes from the dropdown.
            results = get_es_results(group1_name, prefix1, 'authfull', exact=True)
            # A name that finds nobody (a stale dropdown value, or a kind this
            # author has no rows in) leaves nothing to draw. Everything below
            # reads the author's row, so this returns the empty card rather
            # than reaching it with no row at all.
            if results is None:
                return no_author
            data = es_result_pick(results, 'data', None)
            data1 = data[f'{prefix1}_{yr1}']

            names = get_inst_field_cntry(data, prefix1, yr1)
            # The stored country is a lowercase ISO3 code ("usa"), which is
            # what the aggregate lookups key on, but it is not what a reader
            # wants to see. coco turns it into a name for display only; the
            # code itself is still what gets passed to get_es_aggregate below.
            #
            # 16,657 career rows have no country at all, and coco raises on
            # None rather than returning 'not found'. For those the country is
            # left empty, which card_header and share_payload both leave out.
            if names['cntry'] is None:
                cntry_full = None
            else:
                cntry_full = str(coco.convert(names=names['cntry'],
                                              to='name_short'))
                if cntry_full in ('not found', 'None'):
                    cntry_full = str(names['cntry']).upper()
            # A rank means little without its denominator, and the denominator
            # has to be the right one.
            #
            # `rank` is the position in a ranking of EVERY scientist Scopus
            # scored, not of the people on this list. Verified: sorting a
            # career edition by rank leaves c monotonically non-increasing in
            # 100.00% of steps, so it is a strict global ordering by composite
            # score. In career-2024 the largest rank is 1,210,493 against
            # 230,333 published rows, and 48,401 rows (21%) carry a rank
            # larger than the list itself. Those people are published because
            # they are near the top of a SUBFIELD, not of the whole ranking:
            # their median subfield rank is 2,311 out of a median subfield of
            # 131,858.
            #
            # So pairing `rank` with the edition's size produced "ranked
            # 1,210,493 among 230,333 researchers", which is not just
            # unhelpful but visibly impossible, and it is the first thing a
            # reader notices. The subfield pair is a real one: rank_subfield
            # is at most subfield_count in 100.00% of rows.
            span = 'career-long up to' if prefix1 == 'career' else 'in'
            subfield = data1.get('sm-subfield-1')
            sub_rank = data1.get('rank sm-subfield-1')
            sub_total = data1.get('sm-subfield-1 count')
            if sub_rank is not None and sub_total:
                # Components, not markdown: this used to be a markdown string
                # rendered by dcc.Markdown, and moving it into the card put
                # its asterisks on screen. The share image cannot draw
                # components, so it gets the same sentence as plain text.
                standing = [html.Strong(f'{int(sub_rank):,}'), ' of ',
                            html.Strong(f'{int(sub_total):,}'),
                            f' in {subfield}']
                standing_text = (f'{int(sub_rank):,} of {int(sub_total):,} '
                                 f'in {subfield}')
            else:
                # The 2017 and 2018 editions carry no subfield rank at all:
                # 210,026 rows, every one of them. Saying so beats the old
                # fallback, which printed the overall rank instead and so
                # repeated a number already on the card under a label
                # promising a different one.
                standing = 'Not recorded in this edition'
                standing_text = ''
            # Which group the reference marks describe, and the name of it,
            # which the legend has to print: "the median in Stanford
            # University" means something, "the median" does not.
            group_name = {'cntry': names['cntry'],
                          'sm-field': names['field'],
                          'inst_name': names['inst']}.get(uplim or 'cntry',
                                                          names['cntry'])
            #
            # The author's row can lack the very thing it is to be compared
            # by: a missing country or institution names no group at all.
            # get_es_aggregate raises on a missing country and returns {} for
            # a missing institution, so it is not asked. The comparison is
            # then shown as unavailable: no band, no median tick, no legend,
            # and the bars still drawn against the edition maximum.
            if group_name is None:
                kek = {}
            else:
                kek = get_es_aggregate(uplim or 'cntry', group_name, prefix1)
            group_stats = kek.get(f'{prefix1}_{yr1}')
            if group_stats is None:
                group_label = None
            else:
                group_label = {'cntry': cntry_full,
                               'sm-field': names['field'],
                               'inst_name': names['inst']}.get(uplim or 'cntry',
                                                               cntry_full)

            # Which set of columns this reader is looking at.
            suffix_ns = ' (ns)' if ns else ''

            # get_es_aggregate returns [min, q1, median, q3, max, n]. The
            # bullet rows draw the group's median and middle half.
            def _quartiles(metric):
                if group_stats is None:
                    return {}
                vector = group_stats[metric + suffix_ns]
                return {'q1': vector[1], 'median': vector[2], 'q3': vector[3]}

            quartiles = {metric: _quartiles(metric)
                         for metric, _ in WHATIF_METRICS}
            # The score's own quartiles, read rather than summed from the six:
            # a median is not additive, so summing them would not give the
            # group's median score.
            composite_quartiles = _quartiles('c')

            # =============== The two ranks
            #
            # Both numbers are computed here rather than read off the row,
            # because only one of them is published: `rank` counts everyone
            # Scopus scored, and the position on this list has to be counted.
            # Both ranks come from the researcher's own published score, in
            # the same lookup the what-if calculator uses. Counting ranks
            # below theirs would answer the same question and took 94 ms;
            # this takes 7, and it is one code path rather than two that
            # could disagree.
            rank_standing = score_standing(prefix1, yr1,
                                           data1.get('c' + (' (ns)' if ns
                                                            else '')),
                                           ns=ns)

            # =============== What-if state
            #
            # Everything the calculator needs, carried in the browser, so
            # moving an input does not repeat the Elasticsearch lookup that
            # found the author in the first place.
            def _number(value):
                return None if value is None else float(value)

            actual = {metric: _number(data1.get(metric + suffix_ns))
                      for metric, _ in WHATIF_METRICS}
            whatif_state = {
                'kind': prefix1, 'year': yr1, 'ns': bool(ns),
                'name': group1_name,
                'actual': actual,
                'np': _number(data1.get('np')),
                'maxima': composite_maxima(prefix1, yr1, ns=ns),
                'standing': rank_standing,
                'reproducible': composite_is_reproducible(prefix1, yr1),
                'quartiles': {m: {k: _number(v) for k, v in q.items()}
                              for m, q in quartiles.items()},
                'composite_quartiles': {k: _number(v)
                                        for k, v in composite_quartiles.items()},
                'group_label': str(group_label or ''),
            }

            figures = html.Div([_whatif_note(whatif_state)])
            rows = bullet_rows(actual, whatif_state['maxima'], quartiles,
                               composite_quartiles)
            return (figures, whatif_state, False,
                    card_header(group1_name, names['inst'], cntry_full,
                                names['field'], f'{span} {yr1}'),
                    card_chips(round(data1['self%'] * 100, 2), standing),
                    rank_stats(rank_standing['scopus_rank'],
                               rank_standing['within_list'],
                               rank_standing['published']),
                    rank_chart_payload(rank_standing['within_list'],
                                       rank_standing['scopus_rank'],
                                       rank_standing['published']),
                    'ev-id-card',
                    share_payload(group1_name, names['inst'], cntry_full,
                                  names['field'], f'{span} {yr1}',
                                  rank_standing,
                                  round(data1['self%'] * 100, 2),
                                  standing_text),
                    comparison_legend(group_label),
                    bullet_payload(rows, group_label,
                                   reference=group_stats is not None),
                    bullet_inputs(whatif_state))

    # ==========================================================================================
    # The what-if calculator
    # ==========================================================================================
    #
    # Everything here is arithmetic and one index lookup. The composite score
    # is recomputed with the published formula from whatever the reader typed,
    # and the standing is read off the researcher that score lands beside in
    # the same edition. No model, no extrapolation, nothing that could be
    # wrong in a way the page cannot show.

    @callback(
        Output('whatIfTip' + SUFFIX, 'is_open'),
        Output('whatIfTipTimer' + SUFFIX, 'disabled'),
        Output('whatIfTipTimer' + SUFFIX, 'n_intervals'),
        [Input('whatIfToggle' + SUFFIX, 'on'),
         Input('whatIfTipTimer' + SUFFIX, 'n_intervals')]
        + [Input('whatIf-' + metric + SUFFIX, 'value')
           for metric, _ in WHATIF_METRICS],
        State('whatIfStore' + SUFFIX, 'data'),
        prevent_initial_call = True)
    def whatif_tip(on, _ticks, *args):
        """Say the boxes can be typed into, when what-if is switched on.

        Open on the switch, and only where the calculator works for this
        edition. Closed by the timer, by the first edit, or by switching
        what-if off.
        """
        state = args[-1]
        if not state:
            raise PreventUpdate
        if callback_context.triggered_id == 'whatIfToggle' + SUFFIX:
            opening = bool(on) and bool(state.get('reproducible'))
            return opening, not opening, 0
        return False, True, 0

    @callback(
        [Output('bulletStore' + SUFFIX, 'data', allow_duplicate = True),
         Output('whatIf-c' + SUFFIX, 'value'),
           Output('rankDisplay' + SUFFIX, 'children', allow_duplicate = True),
           Output('rankChartStore' + SUFFIX, 'data', allow_duplicate = True),
           Output('idCard' + SUFFIX, 'className', allow_duplicate = True)]
        + [Output('whatIf-' + metric + SUFFIX, 'disabled')
           for metric, _ in WHATIF_METRICS],
        [Input('whatIfToggle' + SUFFIX, 'on')]
        + [Input('whatIf-' + metric + SUFFIX, 'value')
           for metric, _ in WHATIF_METRICS],
        State('whatIfStore' + SUFFIX, 'data'),
        prevent_initial_call = True)
    def apply_whatif(on, *args):
        typed, state = args[:len(WHATIF_METRICS)], args[-1]
        if not state:
            raise PreventUpdate

        live = bool(on) and state['reproducible']
        locked = [not live] * len(WHATIF_METRICS)
        standing = state['standing']

        published_rows = bullet_rows(state['actual'], state['maxima'],
                                     state['quartiles'],
                                     state.get('composite_quartiles'))

        if not live:
            # Back to what was published, on the rows and on the rank at once.
            # Leaving one of them magenta is the failure this guards.
            published_c = composite_score(state['actual'], state['maxima'])
            # A card with no comparison group keeps drawing none: the label
            # is empty exactly when the Explore callback found no group.
            return [
                bullet_payload(published_rows, state['group_label'],
                               reference=bool(state['group_label'])),
                '' if published_c is None else f'{published_c:.2f}',
                rank_stats(standing['scopus_rank'], standing['within_list'],
                           standing['published']),
                rank_chart_payload(standing['within_list'],
                                   standing['scopus_rank'],
                                   standing['published']),
                'ev-id-card',
            ] + locked

        # An emptied box means "leave this one alone", not zero. Someone
        # clearing a field to retype it should not watch the rank collapse
        # between keystrokes.
        values = {}
        for index, (metric, _) in enumerate(WHATIF_METRICS):
            entered = typed[index]
            actual = state['actual'][metric]
            # A box still showing what it was given is a box nobody has
            # edited, so the exact published number is used rather than the
            # rounded one it is displaying. See box_value.
            untouched = (entered is None
                         or (actual is not None
                             and float(entered) == box_value(metric, actual)))
            values[metric] = actual if untouched else max(float(entered), 0.0)

        # An h-index cannot exceed the number of papers. `max` on the input
        # is only advisory, so the cap is applied here as well rather than
        # trusting the browser to have enforced it.
        if state.get('np'):
            ceiling = max(float(state['np']), state['actual']['h'] or 0)
            values['h'] = min(values['h'], ceiling)

        published_c = composite_score(state['actual'], state['maxima'])

        # Nothing edited means the published rank, not a recomputed one.
        #
        # The older editions store the composite score rounded to six
        # decimals: career-2017 has 5.193486 where the six terms add up to
        # 5.193485526. That is a difference of 5e-07, and in a list of
        # 105,026 people somebody is inside it, so recomputing the rank from
        # the parts moved this researcher from 60th to 61st the moment
        # what-if was switched on and before anything had been changed.
        # 2024 stores the full figure and matches exactly.
        untouched = all(values[metric] == state['actual'][metric]
                        for metric, _ in WHATIF_METRICS)
        if untouched:
            new_c, new_standing = published_c, standing
        else:
            new_c = composite_score(values, state['maxima'])
            new_standing = score_standing(state['kind'], state['year'], new_c,
                                          ns = state['ns'])
        return [
            bullet_payload(bullet_rows(values, state['maxima'],
                                       state['quartiles'],
                                       state.get('composite_quartiles')),
                           state['group_label'], whatif = True,
                           published = published_rows,
                           reference = bool(state['group_label']),
                           drag = 'whatIfDrag' + SUFFIX, suffix = SUFFIX),
            '' if new_c is None else f'{new_c:.2f}',
            rank_stats(new_standing['scopus_rank'],
                       new_standing['within_list'],
                       new_standing['published'], whatif = True,
                       was = {'list_rank': standing['within_list'],
                              'scopus_rank': standing['scopus_rank']}),
            rank_chart_payload(new_standing['within_list'],
                               new_standing['scopus_rank'],
                               new_standing['published'], whatif = True),
            'ev-id-card',
        ] + locked

    @callback(
        [Output('whatIf-' + metric + SUFFIX, 'value', allow_duplicate = True)
         for metric, _ in WHATIF_METRICS],
        Input('whatIfDrag' + SUFFIX, 'value'),
        [State('whatIf-' + metric + SUFFIX, 'value')
         for metric, _ in WHATIF_METRICS],
        prevent_initial_call = True)
    def dragged_a_bar(channel, *current):
        """A bar that was dragged puts its number in the box beside it.

        The drag itself is drawn in the browser, so the chart, the composite
        row and the box all move with the mouse without a round trip. This
        runs once, when the handle is let go, and it deliberately does
        nothing but set the box: the recompute that follows is the same one
        typing a number sets off, so there is one path to the score rather
        than two that could disagree.
        """
        parts = str(channel or '').split('|')
        if len(parts) < 2:
            raise PreventUpdate
        metric, value = parts[0], parts[1]
        keys = [key for key, _ in WHATIF_METRICS]
        if metric not in keys:
            raise PreventUpdate
        try:
            number = float(value)
        except ValueError:
            raise PreventUpdate
        out = list(current)
        out[keys.index(metric)] = box_value(metric, max(number, 0.0))
        return out


    offcanvas2 = html.Div(
        [
            dbc.Offcanvas(
                dcc.Markdown(
                    '''
                **Controls**
                * **Exclude self-citations**: recompute every number without the researcher's citations to their own work.
                * **What if**: edit the six indicators and see where the recomputed score would rank.
                * **Compare against**: choose the group (country, field or institution) that the reference marks describe.

                **Reading the bars**
                * Each bar is one indicator relative to the edition maximum, the same term the composite score adds up. The six terms sum to the score.
                * The tick marks the group median, and the shaded band covers the middle half of the group.
                * The last bar is the composite score, divided by six so it fits the same scale.
                    '''
                ),
                id="offcanvas22",
                title="Author metrics",
                is_open=False,
            ),
        ]
    )

    @callback(
        Output("offcanvas22", "is_open"),
        Input("open-offcanvas22", "n_clicks"),
        [State("offcanvas22", "is_open")],
    )
    def toggle_offcanvas(n1, is_open):
        if n1:
            return not is_open
        return is_open

    row3 = html.Div([
        whatIfStore,
        whatIfTipTimer,
        dbc.Row(html.Br()),
        dbc.Row(dbc.Col(html.Div([
            selfC, whatIf, upper,
            dbc.Button("More info", id="open-offcanvas22", n_clicks=0,
                       className="ev-info-btn"),
        ], className="ev-explore-controls"), width = 12)),
        dbc.Row(dbc.Col(html.Div(id='comparisonLegend' + SUFFIX,
                                 className='ev-comparison-legend'), width = 12)),
        metricsFigAuthor_c,
        dbc.Row(html.Br()),
        offcanvas2,
        dbc.Row(dbc.Col(dbc.Container(id = '2author_figs' + SUFFIX), width = {'offset':1,'size':10}))])

    # ========================================================================================== 
    # ========================================================================================== 
    # Layout
    # ========================================================================================== 
    # ========================================================================================== 
    return(html.Div([
        dbc.Container(fluid = True, children = [
            html.Br(),
            row2, 
            dls.GridFade(row3,color="#ECAB4C"), 
        ], className = 'ev-page'), 
    ]))
