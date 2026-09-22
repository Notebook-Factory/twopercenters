"""Matching 66,079 free-text institution names to ROR.

The published data records an institution as whatever string Scopus held,
plus a country, and nothing else: no city, no identifier, no registry. ROR
has all three. What it does not have is any way to be sure a name means the
organisation it looks like it means, so the rules here are built to refuse
rather than to guess, and the tests are mostly about what must NOT match.
"""
import pytest

from pipeline.ror_match import (build_index, choose, name_variants, normalize)


def _entry(ror_id, country, kind='ror_display', city='Somewhere'):
    return {'ror_id': ror_id, 'country': country, 'city': city,
            'lat': 1.0, 'lng': 2.0, 'kind': kind, 'ror_name': ror_id}


# ---------------------------------------------------------------------------
# Normalising
# ---------------------------------------------------------------------------

def test_accents_and_punctuation_do_not_stop_a_match():
    """The data holds "Universidad Tecnica Particular de Loja" and ROR holds
    "Universidad Técnica Particular de Loja"."""
    assert normalize('Universidad Técnica Particular de Loja') == \
        normalize('Universidad Tecnica Particular de Loja')
    assert normalize('St. Jude Children`s Hospital') == \
        normalize('St Jude Children\'s Hospital')


def test_a_leading_the_is_not_part_of_the_name():
    """ROR has "University of British Columbia" and the data has "The
    University of British Columbia". 710 researchers sat behind that word."""
    assert normalize('The University of British Columbia') == \
        normalize('University of British Columbia')


def test_ampersands_read_as_the_word():
    assert normalize('Ear & Eye Hospital') == normalize('Ear and Eye Hospital')


# ---------------------------------------------------------------------------
# Which spellings are worth trying
# ---------------------------------------------------------------------------

def test_the_full_name_is_always_tried_first():
    kinds = [kind for kind, _text in name_variants('University of Oxford')]
    assert kinds[0] == 'name'


def test_a_trailing_department_or_city_is_dropped_on_the_second_try():
    """"Indian Institute of Technology Roorkee, Department of Chemistry" is
    an institution this registry knows plus a unit it does not."""
    variants = dict((kind, text) for kind, text in name_variants(
        'Indian Institute of Technology Roorkee, Department of Chemistry'))
    assert variants['prefix'] == normalize('Indian Institute of Technology '
                                           'Roorkee')


def test_a_parent_before_a_dash_is_not_tried():
    """"ICAR - Central Institute of Freshwater Aquaculture" would match the
    Indian Council of Agricultural Research, whose city is New Delhi and whose
    institute is in Bhubaneswar. The organisation is arguably right and the
    location is wrong, which is worse than no answer for a field whose whole
    purpose is location."""
    texts = [text for _kind, text in name_variants(
        'ICAR - Central Institute of Freshwater Aquaculture')]
    assert normalize('ICAR') not in texts


def test_a_name_with_nothing_to_trim_is_tried_once():
    assert len(name_variants('Stanford University')) == 1


# ---------------------------------------------------------------------------
# Choosing between candidates
# ---------------------------------------------------------------------------

def test_the_country_has_to_agree():
    """The published data's country is the one fact about the institution we
    already have. A candidate that contradicts it is the wrong organisation,
    whatever its name says."""
    assert choose([_entry('ror/a', 'gb')], 'us') is None
    assert choose([_entry('ror/a', 'us')], 'us')['ror_id'] == 'ror/a'


def test_two_organisations_of_the_same_name_in_one_country_are_refused():
    """"College of Engineering" is 1,109 researchers in career-2024 and is
    not an organisation. Picking one of several would put a city on a card
    that is simply invented."""
    assert choose([_entry('ror/a', 'us'), _entry('ror/b', 'us')], 'us') is None


def test_the_same_organisation_under_two_of_its_names_is_not_ambiguous():
    same = [_entry('ror/a', 'us', kind='alias'),
            _entry('ror/a', 'us', kind='ror_display')]
    chosen = choose(same, 'us')
    assert chosen['ror_id'] == 'ror/a'
    # The display name is the one to record, not whichever came first.
    assert chosen['kind'] == 'ror_display'


def test_an_institution_with_no_country_matches_nothing():
    """10,967 career rows carry no institution at all, and a name on its own
    is not enough to identify one."""
    assert choose([_entry('ror/a', 'us')], '') is None


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------

def test_every_name_a_record_is_known_by_is_indexed():
    records = [{
        'id': 'https://ror.org/x',
        'status': 'active',
        'names': [{'value': 'University of Vienna', 'types': ['ror_display',
                                                              'label']},
                  {'value': 'Universität Wien', 'types': ['label']},
                  {'value': 'UNIVIE', 'types': ['acronym']}],
        'locations': [{'geonames_details': {'country_code': 'AT',
                                            'name': 'Vienna',
                                            'lat': 48.2, 'lng': 16.3}}],
    }]
    index = build_index(records)
    for spelling in ('University of Vienna', 'Universitat Wien', 'UNIVIE'):
        assert normalize(spelling) in index, spelling
    entry = index[normalize('University of Vienna')][0]
    assert entry['country'] == 'at'
    assert entry['city'] == 'Vienna'
    assert entry['ror_name'] == 'University of Vienna'


def test_a_withdrawn_record_is_not_indexed():
    """ROR withdraws records. Matching one would attach an identifier that
    the registry itself no longer stands behind."""
    records = [{
        'id': 'https://ror.org/gone',
        'status': 'withdrawn',
        'names': [{'value': 'Gone University', 'types': ['ror_display']}],
        'locations': [{'geonames_details': {'country_code': 'US',
                                            'name': 'Nowhere',
                                            'lat': 0.0, 'lng': 0.0}}],
    }]
    assert build_index(records) == {}


def test_a_closed_organisation_is_still_indexed():
    """ROR marks an organisation that has closed or merged as inactive. This
    data is historical: a 2017 affiliation to an institute that has since
    closed was a real affiliation, and dropping those records cost about 700
    institutions for no gain in correctness."""
    records = [{
        'id': 'https://ror.org/closed',
        'status': 'inactive',
        'names': [{'value': 'Closed Institute', 'types': ['ror_display']}],
        'locations': [{'geonames_details': {'country_code': 'DE',
                                            'name': 'Jena',
                                            'lat': 50.9, 'lng': 11.6}}],
    }]
    assert normalize('Closed Institute') in build_index(records)


# ---------------------------------------------------------------------------
# What ended up in the database
# ---------------------------------------------------------------------------

def test_every_stored_match_agrees_with_the_published_country():
    """The rule the matcher is built on, checked against what it actually
    wrote rather than against itself."""
    from citations_lib.utils import _fetch, iso2
    rows = _fetch('select i.country_code, r.country_code '
                  'from institution_ror r '
                  'join institutions i on i.institution_id = r.institution_id')
    assert rows
    wrong = [(ours, theirs) for ours, theirs in rows
             if iso2(ours) != (theirs or '')]
    assert not wrong, wrong[:5]


def test_a_stored_match_carries_somewhere_to_point_at():
    from citations_lib.utils import _fetch
    rows = _fetch('select count(*) from institution_ror '
                  'where ror_id is null or city is null '
                  'or lat is null or lng is null')
    assert rows[0][0] == 0


def test_only_the_two_intended_spellings_were_used():
    from citations_lib.utils import _fetch
    kinds = {row[0] for row in
             _fetch('select distinct matched_on from institution_ror')}
    assert kinds <= {'name', 'prefix'}


def test_coverage_has_not_collapsed():
    """Floors, not targets. A new ROR release moves these by a little; a
    change to the matcher that breaks it moves them by a lot, and the point
    of the numbers is to notice that."""
    from citations_lib.utils import _fetch
    institutions = _fetch('select count(*) from institutions')[0][0]
    matched = _fetch('select count(*) from institution_ror')[0][0]
    assert matched / institutions > 0.25, f'{matched}/{institutions}'

    covered, total = _fetch(
        "select count(*) filter (where r.institution_id is not null), "
        "count(*) from career_metrics m "
        "left join institution_ror r on r.institution_id = m.institution_id "
        "where m.edition_id = 'career-2024'")[0]
    assert covered / total > 0.60, f'{covered}/{total}'


def _record(ror_id, name, status='active', city='Nowhere', country='US',
            successor=None):
    record = {
        'id': ror_id, 'status': status,
        'names': [{'value': name, 'types': ['ror_display']}],
        'locations': [{'geonames_details': {'country_code': country,
                                            'name': city,
                                            'lat': 1.0, 'lng': 2.0}}],
    }
    if successor:
        record['relationships'] = [{'type': 'successor', 'id': successor}]
    return record


def test_a_withdrawn_record_resolves_to_its_successor():
    """ROR withdrew the record for Harvard Medical School and named Harvard
    University as its successor. That is the registry's own statement about
    where the organisation went, and it is 1,014 researchers in career-2024,
    the largest matched institution on the list."""
    records = [_record('https://ror.org/new', 'Harvard University',
                       city='Cambridge'),
               _record('https://ror.org/old', 'Harvard Medical School',
                       status='withdrawn', city='Boston',
                       successor='https://ror.org/new')]
    index = build_index(records)
    entry = choose(index[normalize('Harvard Medical School')], 'us')
    assert entry['ror_id'] == 'https://ror.org/new'
    # The city is the successor's, which is a real if small error: the school
    # is in Boston and the university is in Cambridge. The flag is how a
    # consumer that cannot accept that filters it out.
    assert entry['city'] == 'Cambridge'
    assert entry['via_successor'] is True
    assert choose(index[normalize('Harvard University')], 'us')['via_successor'] \
        is False


def test_a_withdrawn_record_with_nowhere_to_go_is_dropped():
    records = [_record('https://ror.org/gone', 'Gone University',
                       status='withdrawn')]
    assert build_index(records) == {}


def test_a_successor_that_is_itself_withdrawn_is_not_followed():
    """Otherwise a chain of retractions ends at an identifier ROR does not
    stand behind either."""
    records = [_record('https://ror.org/a', 'A University',
                       status='withdrawn', successor='https://ror.org/b'),
               _record('https://ror.org/b', 'B University',
                       status='withdrawn')]
    assert normalize('A University') not in build_index(records)


def test_an_empty_database_is_not_an_error(tmp_path):
    """The migrations run before the first edition is loaded, and the build
    fixtures create an empty schema on purpose. Reporting a percentage of
    nothing raised ZeroDivisionError and took the whole build down with it."""
    import json as _json

    from pipeline.ror_match import refresh_institution_ror

    dump = tmp_path / 'ror-data.json'
    dump.write_text(_json.dumps([_record('https://ror.org/x', 'Somewhere')]))

    class _Empty:
        """The smallest thing that answers like a connection with nothing in
        it: the table exists, and every query returns no rows."""

        def execute(self, sql, *args):
            class _Result:
                def fetchone(inner):
                    return (1,) if 'information_schema' in sql else (0, 0)

                def fetchall(inner):
                    return []
            return _Result()

        def cursor(self):
            class _Cursor:
                def __enter__(inner):
                    return inner

                def __exit__(inner, *exc):
                    return False

                def executemany(inner, *args):
                    return None
            return _Cursor()

        def commit(self):
            return None

    refresh_institution_ror(_Empty(), str(dump))


# ---------------------------------------------------------------------------
# What the map draws
# ---------------------------------------------------------------------------

def test_city_points_add_up_to_the_edition():
    """Every located researcher lands on exactly one point, and the measures
    are the sums of what those researchers hold. A map is a claim about
    totals, so the totals have to be the real ones."""
    from citations_lib.utils import _fetch, city_points
    points = city_points('career', 2024)
    assert points
    expected = _fetch("""
        select count(*), sum(m.nc), sum(m.np) from career_metrics m
        join institution_ror r on r.institution_id = m.institution_id
        where m.edition_id = 'career-2024'""")[0]
    assert sum(p['researchers'] for p in points) == expected[0]
    assert sum(p['citations'] for p in points) == int(expected[1])
    assert sum(p['papers'] for p in points) == int(expected[2])


def test_every_point_has_somewhere_to_be_drawn():
    from citations_lib.utils import city_points
    for point in city_points('career', 2024):
        assert point['city']
        assert -90 <= point['lat'] <= 90
        assert -180 <= point['lng'] <= 180
        assert point['researchers'] >= 1


def test_the_three_measures_are_not_the_same_number():
    """Switching the measure has to change the map, or the control is a lie."""
    from citations_lib.utils import city_points
    points = city_points('career', 2024)
    order = lambda key: [p['city'] for p in
                         sorted(points, key=lambda q: -q[key])[:10]]
    assert order('researchers') != order('citations')


def test_two_cities_of_one_name_in_one_country_stay_apart():
    """Points are keyed on the coordinates ROR gives, not on the name. There
    are eleven Springfields in the United States."""
    from citations_lib.utils import city_points
    points = city_points('career', 2024)
    keys = [(p['city'], p['country_code'], p['lat'], p['lng']) for p in points]
    assert len(keys) == len(set(keys))
    names = [(p['city'], p['country_code']) for p in points]
    assert len(names) >= len(set(names))


def test_the_map_does_not_use_large_scatter_mode():
    """`large: true` is echarts' optimised path for tens of thousands of
    points. This map has 3,341, and rendered headlessly with it on, every
    point disappeared: the land drew and nothing else. It buys nothing at
    this size and the failure is silent."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert 'large: true' not in MAP_DRAW_JS
    assert "blendMode: 'lighter'" in MAP_DRAW_JS


def test_the_scale_says_what_it_is_measuring():
    """showLabel on its own drew the gradient and no numbers, which is a
    scale that says nothing."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert 'text: [commas(onCountries ? countryLargest : largest)' \
        in MAP_DRAW_JS


def test_the_world_outline_is_here_and_is_a_map():
    """ECharts 5 ships no maps, so this file is the map. It is served from
    assets/ rather than a CDN, and the drawing code fetches it by that path."""
    import json

    from citations_lib.glowmap import MAP_DRAW_JS
    with open('assets/world.geo.json') as handle:
        geo = json.load(handle)
    assert geo['type'] == 'FeatureCollection'
    assert len(geo['features']) > 200
    assert '/assets/world.geo.json' in MAP_DRAW_JS


def test_the_map_reads_the_only_two_controls_there_are():
    """The year track under the map and the dataset toggle above it. There
    was a year radio in a toolbar as well; it said the same thing twice and
    it is gone."""
    import app  # noqa: F401
    from dash._callback import GLOBAL_CALLBACK_MAP
    key = next(k for k in GLOBAL_CALLBACK_MAP if 'glowMapStore' in k)
    inputs = [i['id'] for i in GLOBAL_CALLBACK_MAP[key]['inputs']]
    assert 'glowYear_glowmap_' in inputs
    assert 'careerORSingleYrRadioHOME' in inputs


def test_brightness_runs_with_the_logarithm_of_the_value():
    """London has 4,044 researchers and 54.6 million citations. On a straight
    scale the citations view put almost every city at the dark end and the
    map came back nearly blank; on a plain log scale it came back nearly
    white. The power on the log ratio is what puts the middle back down."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert 'Math.log(1 + values[i]) / ceiling' in MAP_DRAW_JS
    assert 'Math.pow(ratio, 2.2)' in MAP_DRAW_JS


def test_every_point_is_a_real_element():
    """Chunked rendering is what made the points stay behind when the map was
    dragged. Echarts turns it on by itself above 3,000 points and this map
    has 3,341: chunked, the display list holds 917 things, the 217 countries
    and one 700-point chunk, and the other 2,641 points sit in an incremental
    layer that a roam does not re-project. Off, the list holds 3,558 and
    every point moves with the map."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert 'progressive: 0' in MAP_DRAW_JS
    assert 'progressiveThreshold: 100000' in MAP_DRAW_JS


def test_the_lookups_are_cached():
    """Both readings of an edition are asked for again every time the year
    moves, and they are the same rows each time."""
    from citations_lib.utils import city_points, country_points
    assert hasattr(city_points, 'cache_info')
    assert hasattr(country_points, 'cache_info')


def test_country_names_are_converted_in_one_call():
    """country_converter takes about 15 ms a lookup and there are 175 codes,
    so one at a time cost 2.6 seconds on the first view of the map."""
    import time

    from citations_lib.utils import _converted_names
    _converted_names.cache_clear()
    start = time.time()
    names = _converted_names()
    elapsed = time.time() - start
    assert len(names) > 150
    assert elapsed < 1.5, f'{elapsed:.1f}s to convert every country name'



def test_colour_runs_with_the_value_and_not_the_row_number():
    """Echarts' visualMap takes the last data dimension when it is not told
    which one to use. Each point here is [lng, lat, brightness, row], so
    colour ran with a city's position in the array: London, the largest and
    the first row, came out the darkest colour on the scale. Density hid it
    at the whole-world view and it was plain the moment the map was zoomed."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert 'dimension: onCountries ? 0 : 2,' in MAP_DRAW_JS


def test_the_scale_bar_does_not_reach_into_the_map():
    """hoverLink highlights whatever falls in the range under the cursor, so
    running the mouse along the bar made the whole map flare at one end and
    do nothing anywhere else."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert 'hoverLink: false' in MAP_DRAW_JS


def test_the_points_follow_the_zoom():
    """A point is small and faint because at the whole-world view its
    neighbours are on top of it. Zoomed in they come apart, and without this
    the map appeared to fade out as you went closer."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert "chart.on('georoam'" in MAP_DRAW_JS
    assert 'function opacityAt(zoom)' in MAP_DRAW_JS
    assert 'function sizeAt(zoom)' in MAP_DRAW_JS


def test_nothing_on_the_map_animates():
    """Echarts animates an option update by default, so every restyle after a
    zoom was a third of a second of the points easing towards their new size
    while the map underneath had already arrived. They looked out of step
    because they were."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert 'animation: false' in MAP_DRAW_JS


def test_the_map_reads_at_two_granularities():
    """Cities are the located seven tenths of an edition; countries are all
    of it, because every fact row carries a country while only the matched
    ones carry coordinates."""
    from citations_lib.glowmap import MAP_DRAW_JS, map_payload
    payload = map_payload('career', 2024)
    assert len(payload['lat']) > 3000
    assert len(payload['countries']) > 150
    # Both travel together, so changing granularity is a redraw and not
    # another round trip.
    assert "grain === 'country'" in MAP_DRAW_JS
    assert "type: 'map', geoIndex: 0" in MAP_DRAW_JS


def test_the_country_reading_covers_more_than_the_city_one():
    from citations_lib.glowmap import map_payload
    payload = map_payload('career', 2024)
    located = sum(payload['researchers'])
    everyone = sum(c['researchers'] for c in payload['countries'])
    assert everyone > located


def test_country_names_reach_the_map_file():
    """The fact tables carry ISO3 and the outline carries its own spellings:
    'Czech Rep.', 'Lao PDR', 'Dem. Rep. Congo'. 145 of 175 agree without
    help and the rest are named in _MAP_NAMES."""
    import json

    from citations_lib.utils import country_points
    with open('assets/world.geo.json') as handle:
        names = {f['properties']['name'] for f in json.load(handle)['features']}
    points = country_points('career', 2024)
    missing = [p for p in points if p['name'] not in names]
    # Taiwan, Hong Kong and Macau have no feature in this outline at all, and
    # nor do a handful of dependencies. Everything else has to land.
    assert {p['country_code'] for p in missing} <= {
        'TWN', 'HKG', 'MAC', 'KNA', 'MCO', 'SMR', 'MTQ', 'GUF', 'GLP', 'UMI'}
    placed = sum(p['researchers'] for p in points if p['name'] in names)
    assert placed / sum(p['researchers'] for p in points) > 0.98


def test_the_year_track_carries_the_editions_that_exist():
    """Career runs 2017 to 2024; the single-year series has no 2018."""
    from citations_lib.glowmap import year_slider
    assert 2018 in year_slider(True).marks
    assert 2018 not in year_slider(False).marks


def test_the_cities_layer_is_gone():
    """It cost more than everything else on the map put together."""
    import os

    from citations_lib.glowmap import MAP_DRAW_JS
    assert not os.path.exists('assets/urban.geo.json')
    assert 'urban' not in MAP_DRAW_JS


def test_the_wheel_belongs_to_the_page():
    """With roam true the wheel zooms the map, so a reader scrolling the page
    stops dead at the map and it dives to street level instead. The plotly
    map at the top of this page turned its scroll zoom off for exactly that
    reason; this one repeated the mistake."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert "roam: 'move'" in MAP_DRAW_JS
    assert 'roam: true' not in MAP_DRAW_JS


def test_zooming_is_on_buttons_instead():
    """Taking the wheel away leaves no way to zoom unless something replaces
    it."""
    from citations_lib.glowmap import glow_map

    def walk(node):
        yield node
        children = getattr(node, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from walk(child)
        elif children is not None:
            yield from walk(children)

    ids = {getattr(n, 'id', None) for n in walk(glow_map())}
    for name in ('glowZoomIn', 'glowZoomOut', 'glowZoomReset'):
        assert any(isinstance(i, str) and i.startswith(name) for i in ids), name


def test_both_layers_share_one_projection():
    """boundingCoords cropped the south to give the map more room, and it
    also gave the geo a different projection from the one the WebGL scatter
    assumes: those points landed north and east of the land they belong to."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert 'boundingCoords' not in MAP_DRAW_JS


def test_every_roam_frame_repaints():
    """A series with a blend mode is composited on a canvas layer of its own,
    and a layer nothing marks dirty is put back where it was: the map slid
    under a drag and the points stayed behind."""
    from citations_lib.glowmap import MAP_DRAW_JS
    handler = MAP_DRAW_JS[MAP_DRAW_JS.index("chart.on('georoam'"):]
    handler = handler[:handler.index('el.__evFollowZoom')]
    assert 'zr.refresh()' in handler



def test_the_points_are_drawn_by_the_canvas_renderer():
    """The WebGL scatter was tried twice and drew the points off the land
    both times: first because the view was cropped to the inhabited
    latitudes and the two layers projected differently, and again after that
    crop was removed. Whatever else it disagrees about, it is not worth more
    of anyone's time to find out."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert 'scatterGL' not in MAP_DRAW_JS
    assert "type: 'scatter', coordinateSystem: 'geo'" in MAP_DRAW_JS
    with open('app.py') as handle:
        assert 'echarts-gl' not in handle.read()


def test_a_click_can_name_a_country_or_a_city():
    """The map sends 'country|USA' or 'city|London|GBR', with a counter on
    the end so clicking the same place twice is still a change Dash sees."""
    from citations_lib.glowmap import MAP_DRAW_JS
    assert "pick('country|'" in MAP_DRAW_JS
    assert "pick('city|'" in MAP_DRAW_JS
    assert '__evPickCount' in MAP_DRAW_JS
    # The country reading needs the click to reach the region, so the geo
    # cannot be silent.
    assert 'silent: false' in MAP_DRAW_JS


class _Clicked:
    """The callback reads which input fired, which only exists inside a
    callback, so a direct call has to say."""
    triggered_id = 'glowPicked_glowmap_'


def test_clicking_a_city_lists_the_people_in_it():
    import app  # noqa: F401
    import pages.home as home
    original, home.callback_context = home.callback_context, _Clicked()
    try:
        # A click opens the panel whatever it was showing before.
        summary, rows, message, style, _cells, _active = \
            home.click_on_map_update('city|Cambridge|USA|1', True, '2024',
                                     'median', {'display': 'none'})
    finally:
        home.callback_context = original
    assert 'Cambridge' in summary
    assert rows and all(r['RESEARCHER'] for r in rows)
    assert 'researchers' in message
    assert style['display'] == 'block'


def test_clicking_a_country_still_does_what_it_did():
    import app  # noqa: F401
    import pages.home as home
    original, home.callback_context = home.callback_context, _Clicked()
    try:
        summary, rows, _message, _style, _cells, _active = \
            home.click_on_map_update('country|USA|2', True, '2024', 'median',
                                     {'display': 'none'})
    finally:
        home.callback_context = original
    assert 'USA' in summary
    assert 'H-index' in summary
    assert rows


def test_a_city_is_keyed_on_its_country_too():
    """There are eleven Springfields in the United States, and a city name on
    its own does not say which country was clicked."""
    from citations_lib.utils import city_researchers
    british, british_total = city_researchers('London', 'GBR', 'career', 2024,
                                              limit=5)
    canadian, canadian_total = city_researchers('London', 'CAN', 'career',
                                                2024, limit=5)
    assert british_total > canadian_total
    assert {r['RESEARCHER'] for r in british} != {r['RESEARCHER']
                                                  for r in canadian}


def test_the_measures_include_the_h_index_and_name_the_count():
    from citations_lib.glowmap import MEASURES
    labels = dict(MEASURES)
    assert labels['researchers'] == 'Researcher count'
    # The best h-index at a place, not the sum: adding h-indices together
    # produces a number that means nothing.
    assert labels['h'] == 'Top h-index'


def test_the_year_arrows_step_along_the_editions_that_exist():
    import citations_lib.glowmap as module

    class _Context:
        triggered_id = 'glowYearNext_glowmap_'

    marks = {y: {'label': str(y)} for y in (2017, 2019, 2020)}
    original = module.callback_context
    try:
        module.callback_context = _Context()
        assert module._step_a_year(0, 1, 2019, marks) == 2020
        _Context.triggered_id = 'glowYearBack_glowmap_'
        # The single-year series has no 2018, so back from 2019 is 2017.
        assert module._step_a_year(1, 0, 2019, marks) == 2017
    finally:
        module.callback_context = original


def test_the_two_readings_do_not_share_a_colour_ramp():
    """A filled country should never read as a lit city. The lights are warm
    and the countries are a cool single hue, so the two pictures cannot be
    confused at a glance."""
    from citations_lib.glowmap import MAP_DRAW_JS
    ramps = MAP_DRAW_JS[MAP_DRAW_JS.index('inRange: {color: onCountries'):]
    ramps = ramps[:ramps.index('seriesIndex')]
    assert '#35B3CE' in ramps          # the cool ramp, for countries
    assert '#FFD48A' in ramps          # the warm one, for cities


def test_pinch_zooms_but_the_wheel_does_not():
    """A trackpad pinch arrives as a wheel event with ctrlKey set; an
    ordinary wheel does not, and has to keep scrolling the page."""
    from citations_lib.glowmap import MAP_DRAW_JS
    wheel = MAP_DRAW_JS[MAP_DRAW_JS.index("addEventListener('wheel'"):]
    wheel = wheel[:wheel.index('touchstart')]
    assert 'if (!event.ctrlKey) { return; }' in wheel
    assert 'preventDefault' in wheel
    # Touch screens pinch through their own events.
    assert "addEventListener('touchmove'" in MAP_DRAW_JS


def test_the_map_has_no_prose_above_it():
    """What the map shows is what its buttons say. A paragraph explaining
    that the points are cities sat above a map of points on cities."""
    from citations_lib.glowmap import glow_map

    def walk(node):
        yield node
        children = getattr(node, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from walk(child)
        elif children is not None:
            yield from walk(children)

    text = ' '.join(str(getattr(n, 'children', '')) for n in walk(glow_map())
                    if isinstance(getattr(n, 'children', None), str))
    assert 'One point per city' not in text
    assert 'Every city on the list' not in text


def test_the_year_is_one_control_now():
    """The track under the map replaced the radio buttons above it, rather
    than sitting beside them as a second way to say the same thing."""
    import app  # noqa: F401
    import pages.home as home

    def walk(node):
        yield node
        children = getattr(node, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from walk(child)
        elif children is not None:
            yield from walk(children)

    ids = {getattr(n, 'id', None) for n in walk(home.layout)}
    assert 'glowYear_glowmap_' in ids
    assert 'selectYrRadioHOME' not in ids
    # The dataset toggle stays, because the tables beside the map read it.
    assert 'careerORSingleYrRadioHOME' in ids


def test_every_control_the_map_listens_to_is_on_the_page():
    """A callback whose input does not exist never fires, and Dash says
    nothing about it because the app suppresses callback exceptions. That is
    how the map came up blank: the year radio was removed and the callback
    that fetches the points was still listening for it, so the store stayed
    empty and the chart cleared itself.
    """
    import app  # noqa: F401
    from dash._callback import GLOBAL_CALLBACK_MAP

    import pages.home as home

    def walk(node):
        yield node
        children = getattr(node, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from walk(child)
        elif children is not None:
            yield from walk(children)

    on_page = {getattr(n, 'id', None) for n in walk(home.layout)}
    on_page = {i for i in on_page if isinstance(i, str)}

    missing = []
    for key, entry in GLOBAL_CALLBACK_MAP.items():
        referenced = list(entry.get('inputs', [])) + list(entry.get('state', []))
        for item in referenced:
            name = item.get('id')
            if not isinstance(name, str):
                continue          # pattern-matching ids
            if 'glow' not in name and name not in ('careerORSingleYrRadioHOME',):
                continue          # only the map's own wiring is built here
            if name not in on_page:
                missing.append((key[:40], name))
    assert not missing, missing


def test_a_panel_nobody_has_opened_is_not_refreshed():
    """Moving the year refreshes whatever the panel is showing, so it never
    describes a different edition from the map. If it is showing nothing
    there is nothing to refresh, and the queries behind it take about a
    second each."""
    import pytest as _pytest
    from dash.exceptions import PreventUpdate

    import app  # noqa: F401
    import pages.home as home

    class _Context:
        triggered_id = 'glowYear_glowmap_'

    hidden = {'height': '400px', 'display': 'none'}
    shown = {'height': '400px', 'display': 'block'}
    original = home.callback_context
    try:
        home.callback_context = _Context()
        with _pytest.raises(PreventUpdate):
            home.click_on_map_update('city|Cambridge|USA|1', True, '2024',
                                     'median', hidden)
        # Showing something means it has to keep up with the map.
        rows = home.click_on_map_update('city|Cambridge|USA|1', True, '2024',
                                        'median', shown)[1]
        assert rows

        # And a click opens it whatever it was doing before.
        _Context.triggered_id = 'glowPicked_glowmap_'
        rows = home.click_on_map_update('city|Cambridge|USA|1', True, '2024',
                                        'median', hidden)[1]
        assert rows
    finally:
        home.callback_context = original


def test_the_info_button_sits_before_the_theme_switch():
    import app  # noqa: F401
    import pages.home as home

    def walk(node):
        yield node
        children = getattr(node, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from walk(child)
        elif children is not None:
            yield from walk(children)

    order = [getattr(n, 'id', None) for n in walk(home.dede)]
    order = [i for i in order if i in ('off', 'theme-toggle')]
    assert order == ['off', 'theme-toggle']


def test_the_map_controls_are_one_row():
    """Dataset, granularity and measure read as one set of controls rather
    than one at each end of the header."""
    import app  # noqa: F401
    import pages.home as home

    def walk(node):
        yield node
        children = getattr(node, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from walk(child)
        elif children is not None:
            yield from walk(children)

    rows = [n for n in walk(home.navigation_row)
            if getattr(n, 'className', '') == 'ev-glow-measures']
    assert rows and len(rows[0].children) == 3


def test_the_icon_buttons_do_not_depend_on_a_runtime_swap():
    """lucide replaces every <i data-lucide> with an <svg> after render, and
    a click that starts on an element swapped before the mouse comes up
    never becomes a click. Both icon-only buttons on this page needed
    pressing twice because of it; they are CSS masks now, which nothing
    replaces."""
    import app  # noqa: F401
    import pages.home as home

    def walk(node):
        yield node
        children = getattr(node, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from walk(child)
        elif children is not None:
            yield from walk(children)

    for name in ('off', 'map-hint-close'):
        button = next(n for n in walk(home.layout)
                      if getattr(n, 'id', None) == name)
        icon = button.children
        assert 'ev-ic' in getattr(icon, 'className', ''), name
        assert not hasattr(icon, 'data-lucide')


def test_the_row_detail_opens_over_the_table_and_closes():
    import app  # noqa: F401
    import pages.home as home

    class _Context:
        triggered_id = 'worldtitle'

    original = home.callback_context
    try:
        home.callback_context = _Context()
        assert home.show_the_row_card('anything', 0)['display'] == 'block'
        _Context.triggered_id = 'row-card-close'
        assert home.show_the_row_card('anything', 1)['display'] == 'none'
    finally:
        home.callback_context = original


def test_the_table_is_as_tall_as_the_map():
    """It was 300px with the summary printed underneath. The summary is a
    card over it now, so the list can run the height of the map beside it."""
    with open('pages/home.py') as handle:
        source = handle.read()
    assert "'height': '300px'" not in source
    assert "'height': '400px'" not in source
    assert source.count("'height': '560px'") >= 2


def test_the_dataset_toggle_matches_the_buttons_beside_it():
    """It carried orange from a rule that keeps it apart from a cyan year
    picker. On this map the year picker is the track underneath, so there is
    nothing to be told apart from."""
    with open('assets/style.css') as handle:
        css = handle.read()
    scoped = css[css.index('.ev-glow-measures [id^="careerORSingleYr"]'):]
    scoped = scoped[:scoped.index('}')]
    assert 'var(--ev-accent)' in scoped
