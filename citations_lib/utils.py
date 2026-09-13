import numpy as np
import pandas as pd

import plotly.graph_objects as go
from IPython.core.display import display, HTML
from plotly.offline import plot
import plotly.express as px
import plotly.colors
from plotly.subplots import make_subplots
import country_converter as coco
import os
import json
import pickle
import base64
import zlib
import math
from functools import lru_cache

import psycopg
from elasticsearch import Elasticsearch

from dotenv import load_dotenv

from db.connection import connect
from pipeline.institution_aggregate import institution_aggregate_by_name

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

if os.getenv('ELASTICSEARCH_URL'):
    # This one's exposed by dokku
    es = Elasticsearch([os.getenv('ELASTICSEARCH_URL')])
else:
    # If local
    es = Elasticsearch([os.getenv('ES_URL_LOCAL')])

def write_pickle(file,filename):
    with open(filename, 'wb') as handle:
        pickle.dump(file, handle, protocol=pickle.HIGHEST_PROTOCOL)

def write_json(in_file,filename):
    with open(filename, "w") as file:
        json.dump(in_file, file)

def read_json(filename):
    with open(filename, "r") as file:
        data = json.load(file)
        return data


# es_scroll and get_index_cat lived here to page through the old
# `career`/`singleyr` Elasticsearch indices. Nothing calls them any more:
# the last live caller was pages/home.py's country click, which now reads
# Postgres, and every other reference in citations_lib/ is inside
# commented-out code. They are removed rather than kept, because keeping a
# working helper that targets indices a fresh deployment will not have is an
# invitation to reach for it again. Author search goes through
# get_es_results against the `authors` alias, which is the only
# Elasticsearch access left.

def get_all_values_by_key(data, target_key):
    result = []

    if isinstance(data, dict):
        for key, value in data.items():
            if key == target_key:
                result.append(value)
            elif isinstance(value, (dict, list)):
                result.extend(get_all_values_by_key(value, target_key))
    elif isinstance(data, list):
        for item in data:
            result.extend(get_all_values_by_key(item, target_key))

    return result

# ---------------------------------------------------------------------------
# The seam between the dashboard and its data.
#
# The eight layout and page modules only ever reach the data through
# get_es_results, es_result_pick, get_es_aggregate and (formerly)
# base64_decode_and_decompress. Elasticsearch still answers the author
# typeahead, because fuzzy name matching is what it is good at. Everything
# numeric now comes out of Postgres.
#
# One format detail matters throughout: edition_id in Postgres is hyphenated
# ("career-2024"), but the dashboard recovers a year with key.split('_')[-1]
# (see get_auth_years and update_auth_yrs below). Every dict this module hands
# back therefore uses underscore keys, "career_2024" and "career_2024_log",
# exactly as the old compressed blob did. _edition_key() is the one place that
# conversion happens.
# ---------------------------------------------------------------------------

AUTHOR_ALIAS = 'authors'

# The typeahead needs names, not documents. Asking for these seven fields
# instead of the whole _source is the difference between one keystroke
# shipping a few kilobytes and shipping a hundred full documents.
_SOURCE_FIELDS = ['author_id', 'authfull', 'name_normalized', 'inst_name',
                  'cntry', 'sm_field', 'years_present']

_TABLE_BY_KIND = {'career': 'career_metrics', 'singleyr': 'singleyr_metrics'}

# Fact-table columns that are not metrics: they are identifiers, or they get
# resolved to a name through a join.
_NON_METRIC_COLUMNS = {
    'metric_id', 'author_id', 'edition_id', 'institution_id', 'field_id',
    'subfield_1_id', 'subfield_2_id', 'observation_date', 'country_code',
    # Only the 2023 and 2024 editions carry these, and the old blob never
    # did, so no layout has a key for them.
    'np_rw', 'nc_to_rw', 'nc_rw',
}

# pipeline/column_map.py maps the dashboard's column names onto database
# columns. This is the same relation read backwards; only the names that are
# not a plain identity need listing. The " (ns)" suffix is handled separately
# because it applies to about half of them.
_DASHBOARD_NAMES = {
    'self_pct': 'self%',
    'np_cited': 'np cited',
    'rank_subfield': 'rank sm-subfield-1',
    'subfield_count': 'sm-subfield-1 count',
    'field_frac': 'sm-field-frac',
    'subfield_1_frac': 'sm-subfield-1-frac',
    'subfield_2_frac': 'sm-subfield-2-frac',
}

_conn = None


def _db():
    """One connection for the process, reopened if it has gone away."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = connect()
        # Reads only. Autocommit keeps the session from sitting idle inside a
        # transaction between dashboard callbacks.
        _conn.autocommit = True
    return _conn


def close_db():
    """Close this process's connection, if it has one.

    Called at the end of importing app.py, and again from the gunicorn
    post_fork hook in cfg.py. Both exist because of one deployment hazard:
    the Procfile runs gunicorn with --preload, so the master process imports
    the app and then forks the workers. pages/home.py runs two queries at
    import time (the year options and the world map's first frame), which
    opens the module-global connection below in the MASTER. Without this,
    every worker would inherit the same libpq socket and their requests would
    interleave on one connection: protocol errors, and in the bad case one
    request reading another request's result set.

    _db() reopens on demand, so closing here costs one connect per worker on
    its first query and nothing after that.
    """
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None


def _with_reconnect(run):
    """Call run(conn), and if the connection has gone away, drop it and try
    once more on a fresh one.

    Everything that reads the database goes through here. It used to be
    inlined in _fetch, which meant the one caller that does not build its own
    SQL -- _group_rows' institution lookup, which hands the live connection
    to pipeline.institution_aggregate -- was the single query in the
    dashboard that did not self-heal after an idle disconnect.
    """
    global _conn
    for attempt in (1, 2):
        try:
            return run(_db())
        except psycopg.Error:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
            if attempt == 2:
                raise


def _fetch(sql, params=()):
    def run(conn):
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    return _with_reconnect(run)


def _edition_key(edition_id):
    """'career-2024' -> 'career_2024'.

    The dashboard splits these keys on '_' to recover the year, so a hyphen
    here would make key.split('_')[-1] hand back the whole string.
    """
    kind, _, year = edition_id.partition('-')
    return f'{kind}_{year}'


def _dashboard_name(column):
    """Database column name -> the name the layouts index the dict with."""
    if column.endswith('_ns'):
        base, suffix = column[:-3], ' (ns)'
    else:
        base, suffix = column, ''
    return _DASHBOARD_NAMES.get(base, base) + suffix


@lru_cache(maxsize=1)
def _editions():
    """[(edition_id, kind, data_year)] for every edition loaded, in order."""
    return _fetch('select edition_id, kind, data_year from editions '
                  'order by kind, data_year')


def edition_years(kind):
    """The data years present in Postgres for 'career' or 'singleyr'.

    The dropdown-index-to-year maps used to be six hardcoded copies that
    stopped at 2021. They are derived from this instead, so loading an
    edition is all it takes to make that year selectable.
    """
    return [year for _, k, year in _editions() if k == kind]


def edition_ids(kind):
    """Edition ids for one kind, in the same ascending-year order as the
    radio indices."""
    return [edition_id for edition_id, k, _ in _editions() if k == kind]


# The twelve metrics the aggregate/info_*.pkl files carry statistics for,
# named as the dashboard names them, paired with their database column.
_DROPDOWN_METRICS = [
    ('nc', 'nc'), ('h', 'h'), ('hm', 'hm'),
    ('ncs', 'ncs'), ('ncsf', 'ncsf'), ('ncsfl', 'ncsfl'),
    ('nc (ns)', 'nc_ns'), ('h (ns)', 'h_ns'), ('hm (ns)', 'hm_ns'),
    ('ncs (ns)', 'ncs_ns'), ('ncsf (ns)', 'ncsf_ns'),
    ('ncsfl (ns)', 'ncsfl_ns'),
]

_COUNTRY_NAMES = {}


def _country_full_name(code):
    """The display name for an ISO3 code, or None if there isn't one.

    Four codes in the data are defunct states that country_converter cannot
    resolve: csk (Czechoslovakia), scg (Serbia and Montenegro), sux (the
    Soviet Union) and ant (the Netherlands Antilles). The pickles left them
    out of the country dropdown and so does this, since the label would read
    'not found' and selecting one would fail the same conversion in
    get_es_aggregate. get_world_df excludes the same four for the same
    reason (FINDING 5).
    """
    if code not in _COUNTRY_NAMES:
        name = coco.convert(names=code, to='name_short')
        _COUNTRY_NAMES[code] = None if name == 'not found' else name
    return _COUNTRY_NAMES[code]


def _dropdown_lists(kind):
    """{edition_id: {'cntry': [...], 'cntry_full': [...], 'inst_name': [...],
    'sm-field': [...]}}: the option lists the group dropdowns offer.

    Read from the dropdown_options materialized view (migration 007) rather
    than by scanning both fact tables. The distinct values do not change
    between builds, and scanning 2.7M rows for them inside a page-building
    callback was the bulk of load_dropdown_opts()'s cost. The view is
    refreshed at the end of a build, next to group_metrics.
    """
    out = {}
    for edition_id, option_kind, value in _fetch(
            'select o.edition_id, o.option_kind, o.option_value '
            'from dropdown_options o '
            'join editions e on e.edition_id = o.edition_id '
            'where e.kind = %s '
            'order by o.edition_id, o.option_kind, o.option_value',
            (kind,)):
        out.setdefault(edition_id, {}).setdefault(option_kind, []).append(value)
    for lists in out.values():
        pairs = [(code, _country_full_name(code))
                 for code in lists.get('cntry', [])]
        pairs = [(code, name) for code, name in pairs if name is not None]
        # The two lists are zipped together to label the country dropdown, so
        # they have to stay aligned.
        lists['cntry'] = [code for code, _ in pairs]
        lists['cntry_full'] = [name for _, name in pairs]
    return out


def _int_if_whole(value):
    """Keep the type the fact-table column had.

    h, nc, ncs and friends are integer columns, so before migration 007 their
    min and max came back as Python ints. dropdown_stats stores every
    statistic as double precision for one uniform column type, so whole
    values are handed back as ints here and fractional ones (hm) are left
    alone.
    """
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _dropdown_stats(kind):
    """{edition_id: {'nc min': ..., 'nc max': ..., 'nc mean': ...,
    'nc std': ...}}, one entry per metric, as the pickles held them.

    Read from the dropdown_stats materialized view (migration 007); see
    _dropdown_lists for why.
    """
    wanted = {column: name for name, column in _DROPDOWN_METRICS}
    out = {}
    for edition_id, metric, minimum, maximum, mean, std in _fetch(
            'select s.edition_id, s.metric, s.min_value, s.max_value, '
            's.mean_value, s.std_value from dropdown_stats s '
            'join editions e on e.edition_id = s.edition_id '
            'where e.kind = %s', (kind,)):
        name = wanted.get(metric)
        if name is None:
            continue
        stats = out.setdefault(edition_id, {})
        stats[f'{name} min'] = _int_if_whole(minimum)
        stats[f'{name} max'] = _int_if_whole(maximum)
        # The pickles stored these rounded to two decimals.
        stats[f'{name} mean'] = None if mean is None else round(float(mean), 2)
        stats[f'{name} std'] = None if std is None else round(float(std), 2)
    return out


@lru_cache(maxsize=1)
def load_dropdown_opts():
    """The dict the two group pages used to build from aggregate/info_*.pkl.

    Those pickles are one file per edition and only nine of them were ever
    generated, so they cover radio indices career 0-4 and singleyr 0-3. Once
    the year radio started offering 2022, 2023 and 2024, filling a group
    dropdown asked for 'career 5' and raised KeyError (RULING R25). This
    computes the same dict for every edition actually loaded.

    The shape is the pickles' shape: outer keys '<kind> <radio index>' in
    ascending data-year order, and inside each, '<metric> min' / ' max' /
    ' mean' / ' std' for the twelve metrics, plus the 'cntry', 'cntry_full',
    'inst_name' and 'sm-field' option lists.

    One pickle key is deliberately not reproduced: 'authfull', the full list
    of author names in that edition. Nothing reads it (the one reference, at
    author_vs_group_layout.py:173, is commented out), and it is by far the
    most expensive part: about 200,000 names per edition, so 15 editions
    would be roughly three million strings built at page-construction time,
    in each of the two layouts that call this.
    """
    opts = {}
    for kind in ('career', 'singleyr'):
        lists = _dropdown_lists(kind)
        stats = _dropdown_stats(kind)
        for index, edition_id in enumerate(edition_ids(kind)):
            entry = dict(stats.get(edition_id, {}))
            entry.update(lists.get(edition_id, {}))
            opts[f'{kind} {index}'] = entry
    return opts


def yr_convention_map(career):
    """{"0": "2017", "1": "2018", ...}: radio index -> year, as a string.

    This replaces the hardcoded yr_convention_r dicts in
    group_vs_group_layout.py and the two *_yr_convention dicts in
    author_vs_group_layout.py (which are this map inverted). The index is the
    position in update_yr_options()'s list and both are built from
    edition_years(), so the two cannot drift apart.
    """
    kind = 'career' if career else 'singleyr'
    return {str(i): str(year) for i, year in enumerate(edition_years(kind))}


@lru_cache(maxsize=1)
def _maxima():
    """{edition_id: {column: max}} from metric_maxima.

    A log-transformed copy of every table used to be stored next to the raw
    one. Those are computed at read time now, from these maxima, which is why
    the *_log dicts below exist with no *_log table behind them.
    """
    out = {}
    for edition_id, metric, max_value in _fetch(
            'select edition_id, metric, max_value from metric_maxima'):
        out.setdefault(edition_id, {})[metric] = max_value
    return out


def _log_transform(value, maximum):
    """log(x + 1) / log(max + 1), the transform the *_LogTransform pickles
    held. Returns None when it is not defined."""
    if value is None or maximum is None or maximum <= 0:
        return None
    try:
        denominator = math.log(float(maximum) + 1)
        if denominator <= 0:
            return None
        return math.log(float(value) + 1) / denominator
    except (ValueError, TypeError):
        return None


@lru_cache(maxsize=8)
def _column_names(table):
    with _db().cursor() as cur:
        cur.execute(f'select * from {table} limit 0')
        base = [d.name for d in cur.description]
    return tuple(base) + ('inst_name', 'field_name', 'subfield_1_name',
                          'subfield_2_name')


@lru_cache(maxsize=2048)
def _author_rows(author_ids, kind):
    table = _TABLE_BY_KIND[kind]
    rows = _fetch(
        f'select m.*, i.inst_name, f.name as field_name, '
        f's1.name as subfield_1_name, s2.name as subfield_2_name '
        f'from {table} m '
        f'left join institutions i on i.institution_id = m.institution_id '
        f'left join fields f on f.field_id = m.field_id '
        f'left join subfields s1 on s1.subfield_id = m.subfield_1_id '
        f'left join subfields s2 on s2.subfield_id = m.subfield_2_id '
        f'where m.author_id = any(%s) '
        f'order by m.edition_id',
        (list(author_ids),))
    return _column_names(table), rows


def _author_data(author_ids, kinds):
    """The nested dict the compressed blob used to hold, for one author.

    Keyed "<kind>_<year>" and "<kind>_<year>_log", each holding one flat dict
    of dashboard metric names.
    """
    data = {}
    for kind in kinds:
        columns, rows = _author_rows(tuple(author_ids), kind)
        position = {name: i for i, name in enumerate(columns)}
        for row in rows:
            edition_id = row[position['edition_id']]
            key = _edition_key(edition_id)
            if key in data:
                # Two author_ids that share a display name both claim this
                # edition. The richer one came first; keep it.
                continue
            maxima = _maxima().get(edition_id, {})
            plain = {
                'inst_name': row[position['inst_name']],
                'cntry': row[position['country_code']],
                'sm-field': row[position['field_name']],
                'sm-subfield-1': row[position['subfield_1_name']],
                'sm-subfield-2': row[position['subfield_2_name']],
            }
            logged = dict(plain)
            for column, index in position.items():
                if column in _NON_METRIC_COLUMNS or column.endswith('_name'):
                    continue
                value = row[index]
                if value is None:
                    continue
                name = _dashboard_name(column)
                plain[name] = value
                transformed = _log_transform(value, maxima.get(column))
                if transformed is not None:
                    logged[name] = transformed
            data[key] = plain
            data[f'{key}_log'] = logged
    return data


@lru_cache(maxsize=512)
def _group_rows(group, group_value, kind):
    """(edition_id, metric, min, q1, median, q3, max, n) for one group.

    'cntry' and 'sm-field' come from the group_metrics materialized view.
    'inst_name' is computed live instead: materialising institutions measured
    7.4M rows and 1.65GB with a 45-minute locking refresh, while one indexed
    lookup answers in milliseconds. See pipeline/institution_aggregate.py.
    """
    if group == 'inst_name':
        live = _with_reconnect(
            lambda conn: institution_aggregate_by_name(conn, group_value, kind))
        return [(edition_id, metric, mn, q1, median, q3, mx, n)
                for edition_id, _, _, metric, mn, q1, median, q3, mx, n
                in live]
    return _fetch(
        'select g.edition_id, g.metric, g.min, g.q1, g.median, g.q3, '
        'g.max, g.n from group_metrics g '
        'join editions e on e.edition_id = g.edition_id '
        'where g.group_kind = %s and g.group_value = %s and e.kind = %s',
        (group, group_value, kind))


def _group_data(group, group_value, kind):
    data = {}
    for edition_id, metric, mn, q1, median, q3, mx, n in _group_rows(
            group, group_value, kind):
        key = _edition_key(edition_id)
        name = _dashboard_name(metric)
        vector = [mn, q1, median, q3, mx, n]
        data.setdefault(key, {})[name] = vector
        maximum = _maxima().get(edition_id, {}).get(metric)
        # The count in slot 5 is not a measurement of the metric, so it is
        # carried through untransformed.
        data.setdefault(f'{key}_log', {})[name] = [
            _log_transform(v, maximum) for v in vector[:5]] + [n]
    return data


def _requested_kinds(idx_name):
    """idx_name used to name an Elasticsearch index. Read it as a kind, or a
    list of kinds, and ignore anything else."""
    if isinstance(idx_name, str):
        candidates = [idx_name]
    elif isinstance(idx_name, (list, tuple, set)):
        candidates = list(idx_name)
    else:
        candidates = []
    kinds = [k for k in candidates if k in _TABLE_BY_KIND]
    return kinds or ['career', 'singleyr']


def es_result_pick(result, field, nohit=[''], expect_name=None):
    """Pull one field out of a get_es_results() frame.

    field='data' is the interesting case: it no longer decompresses a blob
    out of the search hit, it reads that author's rows from Postgres and
    assembles the same nested dict.

    The 'data' branch used to take `result['_source.authfull'].iloc[0]`
    outright, and the frame is sorted by edition count across every matched
    name, so whichever near-match happened to have the most editions won:
    asking for 'Muller, Markus' returned 'Mullner, Markus', and asking for
    'Garcia, David' returned 'Garcia, David A.'. Passing exact=True to
    get_es_results avoids that, but only as long as every caller remembers
    to, and one omission puts a stranger's citation record back under a real
    researcher's name.

    So the check lives here instead. get_es_results records the name it was
    asked for on the frame (`frame.attrs['requested_name']`), and callers can
    also state it directly with expect_name. When a requested name is known,
    the rows used are the rows carrying exactly that name, never row 0
    whatever it says, and if the frame holds no row with that name this
    raises rather than returning someone else's numbers.
    """
    if result is None or len(result) == 0:
        return nohit
    if field == 'data':
        # The old index held one document per author name covering every year
        # that name appeared, and the layouts still look a name up and expect
        # all of its editions back. Identity resolution can now split one
        # display name across several author_ids, so gather every hit
        # carrying the requested name, richest first.
        names = result['_source.authfull']
        if expect_name is None:
            expect_name = result.attrs.get('requested_name')
        if expect_name is None:
            # No name was recorded: the frame did not come from a by-name
            # lookup (get_es_aggregate's country/field frames land here), so
            # there is nothing to check it against.
            wanted = names.iloc[0]
        else:
            wanted = expect_name
            if not (names == wanted).any():
                raise ValueError(
                    "es_result_pick(result, 'data'): no row in this frame is "
                    f"{wanted!r}. The frame holds "
                    f"{list(dict.fromkeys(names))!r}. Returning the top row "
                    "here would report another author's citation record "
                    f"under {wanted!r}; if a fuzzy search cannot find the "
                    "name, the honest answer is no data. Look the name up "
                    "with get_es_results(..., exact=True)."
                )
        same_name = result[names == wanted]
        author_ids = tuple(dict.fromkeys(same_name['_source.author_id']))
        kinds = tuple(dict.fromkeys(same_name['_index']))
        data = _author_data(author_ids, kinds)
        return data if data else nohit
    if f'_source.{field}' in result.keys():
        # One author produces one row per kind, so the same name can appear
        # twice; the dropdown must not show it twice because of that.
        return list(dict.fromkeys(result[f'_source.{field}']))
    return nohit

def get_auth_years(data):
    #data = es_result_pick(result,'data', None)
    if data:
        years = []
        for dat in data.keys():
            if dat.split('_')[-1] != 'log':
                years.append(dat.split('_')[-1])
        return years
    else:
        return None

@lru_cache(maxsize=64)
def edition_author_count(kind, year):
    """How many researchers are in one edition.

    The rank shown beside an author means little on its own: 4,812 is very
    different out of 5,000 than out of 200,000. This is the denominator for
    that sentence, cached because it is one count per edition and the answer
    does not change between requests.
    """
    if kind not in _TABLE_BY_KIND:
        return None
    rows = _fetch(f'select count(*) from {_TABLE_BY_KIND[kind]} '
                  f'where edition_id = %s', (f'{kind}-{year}',))
    return rows[0][0] if rows else None


def country_researchers(country, kind, year):
    """[{'INSTITUTE': ..., 'RESEARCHER': ...}] for one country and edition.

    pages/home.py used to answer the map's country click by scrolling the
    legacy `career`/`singleyr` Elasticsearch indices and filtering on a
    `years` field in each document. Those indices stop at 2021 and are only
    still on the machine as the latency benchmark's baseline, so clicking a
    country with 2022, 2023 or 2024 selected listed nobody at all. This is
    the same question asked of Postgres, which is where the fact rows live.

    `country` is whatever the choropleth handed back; coco.convert is
    idempotent on an ISO3 code, so the same conversion get_es_aggregate does
    is applied here and the two always agree on the country key.
    """
    if kind not in _TABLE_BY_KIND:
        return []
    table = _TABLE_BY_KIND[kind]
    code = str(coco.convert(names=country, to='ISO3')).lower()
    rows = _fetch(
        f'select a.authfull_display, i.inst_name '
        f'from {table} m '
        f'join authors a on a.author_id = m.author_id '
        f'left join institutions i on i.institution_id = m.institution_id '
        f'where m.country_code = %s and m.edition_id = %s '
        f'order by a.authfull_display',
        (code, f'{kind}-{year}'))
    return [{'INSTITUTE': inst_name or '', 'RESEARCHER': authfull}
            for authfull, inst_name in rows]


def get_es_aggregate(group,group_name,prefix):
    """Summary vectors for one country, field or institution.

    Returns {"<prefix>_<year>": {metric: [min, q1, median, q3, max, n]}} plus
    a "_log" copy of each, the same shape for all three groups, so callers
    cannot tell that institutions are computed live and the other two come
    out of a materialized view.
    """
    if group == 'cntry':
        # The dashboard passes either a full country name or the lowercase
        # ISO3 code it read out of an author row. group_metrics is keyed by
        # the latter, and coco.convert is idempotent on a code.
        return _group_data(
            'cntry', str(coco.convert(names=group_name, to='ISO3')).lower(),
            prefix)
    if group == 'sm-field':
        return _group_data('sm-field', group_name, prefix)
    if group == 'inst_name':
        return _group_data('inst_name', group_name, prefix)
    return {}

# The seven fields build_search_index.py puts in each Elasticsearch document,
# rebuilt for one name straight from the tables they were indexed from. It is
# the same shape as that module's _AUTHORS_QUERY, narrowed to the authors
# whose normalized name matches, so the two cannot describe an author
# differently: "the most recent fact row decides inst/cntry/field, and
# years_present is every edition the author has a row in".
_EXACT_NAME_QUERY = """
with matched as (
    select author_id, authfull_display, name_normalized
    from authors
    where authfull_display = %s
),
unioned as (
    select c.author_id, c.edition_id, c.institution_id, c.field_id,
           c.country_code, c.observation_date
    from career_metrics c join matched m on m.author_id = c.author_id
    union all
    select s.author_id, s.edition_id, s.institution_id, s.field_id,
           s.country_code, s.observation_date
    from singleyr_metrics s join matched m on m.author_id = s.author_id
),
ranked as (
    select unioned.*,
           row_number() over (
               partition by author_id order by observation_date desc, edition_id desc
           ) as rn
    from unioned
),
latest as (
    select author_id, institution_id, field_id, country_code
    from ranked where rn = 1
),
years as (
    select author_id, array_agg(distinct edition_id order by edition_id) as years_present
    from unioned group by author_id
)
select m.author_id, m.authfull_display, m.name_normalized, i.inst_name,
       l.country_code, f.name, coalesce(y.years_present, '{}')
from matched m
left join latest l on l.author_id = m.author_id
left join institutions i on i.institution_id = l.institution_id
left join fields f on f.field_id = l.field_id
left join years y on y.author_id = m.author_id
"""


def _authors_by_exact_name(name):
    """Authors whose display name is exactly `name`, shaped like ES hits.

    Elasticsearch is kept for fuzzy search, and this is not search. By the
    time the dashboard fetches an author's metrics the user has already
    picked a name out of the dropdown, so the exact string is in hand, and
    fuzzy-matching a string you already have exactly is work with no
    purpose. That work was 79% of the fetch cost, because the fuzzy
    multi_match scores candidates across all 818,667 documents in the
    `authors` alias. Postgres answers the same question with one indexed
    read of `authors_authfull_display_idx`.

    Matching is on `authfull_display`, the exact string the typeahead hands
    back, indexed by migration 006. It deliberately does not go through
    `name_normalized`: build_relational.py writes one `authors` row per
    author_id while the same author's raw name can be spelled differently in
    different editions, so a stored name_normalized may have come from a
    different edition's spelling than the stored authfull_display. Matching
    the display string needs no agreement between the two.

    One display name can resolve to several author_ids (identity resolution
    splits genuinely different people who share a name), which is why this
    returns a list; es_result_pick orders them richest-first.

    `_score` is 1.0 for every row: these are exact matches, so there is no
    relevance to rank by, and es_result_pick orders by edition count anyway.
    """
    rows = _fetch(_EXACT_NAME_QUERY, (name,))
    return [{
        '_id': author_id,
        '_score': 1.0,
        '_source': {
            'author_id': author_id,
            'authfull': authfull,
            'name_normalized': name_normalized,
            'inst_name': inst_name,
            'cntry': cntry,
            'sm_field': sm_field,
            'years_present': list(years_present or []),
        },
    } for (author_id, authfull, name_normalized, inst_name, cntry,
           sm_field, years_present) in rows]


def get_es_results(search_term,idx_name, search_fields, exact = False):
    """Search authors by name. Still Elasticsearch, still fuzzy.

    Fuzzy name matching is the reason Elasticsearch survived the migration,
    so the multi_match with fuzziness "auto" is unchanged. Two things did
    change. There is one `authors` alias now instead of an index per kind, so
    idx_name no longer names an index: it is read as which kind the caller
    wants, either 'career' / 'singleyr' (restricting the frame to authors who
    have that kind, which is how single_author_layout still learns an author
    has no single-year data) or ['career', 'singleyr'] for both. And _source
    is filtered, so a keystroke no longer ships a hundred full documents.

    Task-10 remedy (RULING R14, typeahead p50 regression): `size` dropped
    from 100 to 30. The unified `authors` alias holds 818,667 documents
    against the legacy `career` index's 270,910, so the same fuzzy
    multi_match now scores three times as many candidates and, worse, a
    caller requesting both kinds used to get at most 100 rows total (one ES
    query across two indices); against the single alias it could get up to
    100 hits x 2 kinds = 200 rows built and DataFrame-sorted below. Neither
    the typeahead dropdown nor the radio-enabling callback in
    callback_templates.py needs anywhere near 100 relevance-ranked
    candidates; fuzziness itself is untouched.
    """
    if not search_term:
        return None
    kinds = _requested_kinds(idx_name)
    if exact:
        if search_fields == 'authfull':
            return _frame_from_hits(_authors_by_exact_name(search_term), kinds,
                                    requested_name=search_term)
        query = {"term": {search_fields: search_term}}
    else:
        query = {
            "multi_match": {
                "query": search_term,
                #"type": "phrase_prefix",
                "operator": "and",
                "fuzziness": "auto",
                "fields": search_fields
            },
        }
    result = es.search(index=AUTHOR_ALIAS, size=30,
                       body={"query": query, "_source": _SOURCE_FIELDS,
                             # Nobody here reads hits.total: get_es_results
                             # uses hits only. Left at the default,
                             # Elasticsearch counts matches up to 10,000
                             # before it can stop, which on a fuzzy query
                             # over the 818,667-document alias means scoring
                             # far more documents than the 30 that are
                             # returned. Turning the count off lets Lucene
                             # skip documents that cannot reach the top 30.
                             # The hits themselves are unchanged: every one
                             # of the 15 terms checked returned the same
                             # ids in the same order with the same scores.
                             "track_total_hits": False})
    hits = result.get('hits', {}).get('hits', [])
    if not hits:
        return None
    # A name lookup records the name it was asked for on the frame, so that
    # es_result_pick(result, 'data') reads that author's rows and not
    # whichever near-match happens to sort first. Searches on other fields
    # (cntry, sm-field) record nothing: there is no author name in play.
    return _frame_from_hits(
        hits, kinds,
        requested_name=search_term if search_fields == 'authfull' else None)


def _frame_from_hits(hits, kinds, requested_name=None):
    """One row per (hit, kind) the hit actually has data for.

    Shared by the fuzzy Elasticsearch path and the exact Postgres path so
    both hand callers the identical frame; a hit is {'_id', '_score',
    '_source'} from either source.

    `requested_name` is carried on the frame as `attrs['requested_name']`.
    It is the name the caller asked for, which is not always the name the
    first row carries: the frame is sorted by edition count across every
    matched name, so a fuzzy search for 'Garcia, David' puts 'Garcia, David
    A.' first. es_result_pick reads it to make sure it hands back the
    requested author's record rather than that one.
    """
    records = []
    for hit in hits:
        source = hit['_source']
        years = source.get('years_present', [])
        # years_present holds hyphenated edition ids, so the kind is what
        # comes before the hyphen.
        present = {edition.partition('-')[0] for edition in years}
        matched = [kind for kind in kinds if kind in present]
        if not matched:
            continue
        # Built once per hit rather than once per (hit, kind): a two-kind
        # caller used to re-flatten the same _source twice.
        base = {f'_source.{key}': value for key, value in source.items()}
        # callback_templates reads result['_index'] and looks for the
        # literal strings 'career' and 'singleyr' in it to decide which
        # radio buttons to enable. That used to be the index name. It is
        # seeded here, before the three keys below, so that the frame's
        # column order is the same as when each record was built inline.
        base['_index'] = None
        base['_id'] = hit['_id']
        base['_score'] = hit['_score']
        base['_editions'] = len(years)
        for kind in matched:
            record = dict(base)
            record['_index'] = kind
            records.append(record)
    if not records:
        return None
    # Hits arrive in relevance order. Within one name, prefer the author_id
    # that covers the most editions, so es_result_pick(result, 'data') reads
    # the fuller record when identity resolution split a display name.
    #
    # list.sort is stable, like the sort_values(kind='stable') this replaces,
    # so relevance order still breaks ties. Sorting the records before the
    # frame is built saves a sort_values pass and a reset_index pass over a
    # freshly constructed DataFrame; from_records on an already-ordered list
    # produces the same RangeIndex reset_index(drop=True) produced.
    records.sort(key=lambda record: -record['_editions'])
    frame = pd.DataFrame.from_records(records)
    if requested_name is not None:
        frame.attrs['requested_name'] = requested_name
    return frame

def base64_decode_and_decompress(encoded_data,flg=True):
    """Dead as of the Postgres migration: nothing stores compressed blobs.

    Kept rather than deleted so that a caller nobody noticed fails here with
    a message that names its replacement, instead of failing somewhere
    downstream with a confusing KeyError.
    """
    raise RuntimeError(
        "base64_decode_and_decompress is gone: author data is no longer a "
        "compressed blob in Elasticsearch. Use es_result_pick(result, "
        "'data'), which assembles the same dict from Postgres."
    )

def get_metric_long_name(career, yr, metric, include_year = True):
    # This list used to be hardcoded as [2017, 2018, 2019, 2020, 2021], one
    # of the six hardcoded year lists the migration replaced everywhere
    # else. update_yr_options() now offers 2022, 2023 and 2024 because it is
    # derived from the editions table, so picking one of those years reached
    # this function with yr=5, 6 or 7 and raised IndexError off the end of
    # the five-element list. Deriving it from the same table is what the
    # rest of the module already does.
    #
    # The indexing convention is unchanged: yr indexes the career year list,
    # and a single-year yr is bumped by one because the single-year series
    # has no 2018 edition while the career series does.
    yrs = edition_years('career')
    if yr != 0 and career == False: yr = yr + 1
    year = yrs[yr]
    if include_year == True: metric_name_dict = {
        'authfull':'author name',
        'inst_name':'institution name (large institutions only)',
        'cntry':'country associated with most recent institution',
        'np':f'number of papers from 1960 to {year}',
        'firstyr':'year of first publication',
        'lastyr':'year of most recent publication',
        'rank (ns)':'rank based on composite score c', 
        'nc (ns)':f'total cites from 1996 to {year}', 
        'h (ns)':f'h-index as of the end of {year}', 
        'hm (ns)':f'hm-index as of end-{year}',
        'nps (ns)':'number of single authored papers',
        'ncs (ns)':'total cites to single authored papers', 
        'cpsf (ns)':'number of single + first authored papers', 
        'ncsf (ns)':'total cites to single + first authored papers', 
        'npsfl (ns)':'number of single + first + last authored papers', 
        'ncsfl (ns)':'total cites to single + first + last authored papers',
        'c (ns)':'composite score', 
        'npciting (ns)':'number of distinct citing papers', 
        'cprat (ns)':'ratio of total citations to distinct citing papers', 
        'np cited (ns)':f'number of papers 1960-{year} that have been cited at least once (1996-{year})',
        'self%':'self-citation percentage', 
        'rank':'rank based on composite score c', 
        'nc':f'total cites 1996-{year}', 
        'h':f'h-index as of end-{year}',
        'hm':f'hm-index as of end-{year}', 
        'nps':'number of single authored papers',
        'ncs':'total cites to single authored papers', 
        'cpsf':'number of single + first authored papers', 
        'ncsf':'total cites to single + first authored papers', 
        'npsfl':'number of single + first + last authored papers', 
        'ncsfl':'total cites to single + first + last authored papers',
        'c':'composite score', 
        'npciting':'number of distinct citing papers', 
        'cprat':'ratio of total citations to distinct citing papers', 
        'np cited':f'number of papers 1960-{year} that have been cited at least once (1996-{year})',
        'np_d':f'# papers 1960-{year} in titles that are discontinued in Scopus', 
        'nc_d':f'total cites 1996-{year} from titles that are discontinued in Scopus', 
        'sm-subfield-1':'top ranked Science-Metrix category (subfield) for author', 
        'sm-subfield-1-frac':'associated category fraction',
        'sm-subfield-2':'second ranked Science-Metrix category (subfield) for author', 
        'sm-subfield-2-frac':'associated category fraction', 
        'sm-field':'top ranked higher-level Science-Metrix category (field) for author', 
        'sm-field-frac':'associated category fraction',
        'rank sm-subfield-1':'rank of c within category sm-subfield-1', 
        'rank sm-subfield-1 (ns)':'rank of c (ns) within category sm-subfield-1', 
        'sm-subfield-1 count':'total number of authors within category sm-subfield-1'}
    else: metric_name_dict = {
        'authfull':'author name',
        'inst_name':'institution name (large institutions only)',
        'cntry':'country associated with most recent institution',
        'np':f'number of papers',
        'firstyr':'year of first publication',
        'lastyr':'year of most recent publication',
        'rank (ns)':'rank based on composite score c', 
        'nc (ns)':f'total cites', 
        'h (ns)':f'h-index', 
        'hm (ns)':f'hm-index',
        'nps (ns)':'number of single authored papers',
        'ncs (ns)':'total cites to single authored papers', 
        'cpsf (ns)':'number of single + first authored papers', 
        'ncsf (ns)':'total cites to single + first authored papers', 
        'npsfl (ns)':'number of single + first + last authored papers', 
        'ncsfl (ns)':'total cites to single + first + last authored papers',
        'c (ns)':'composite score', 
        'npciting (ns)':'number of distinct citing papers', 
        'cprat (ns)':'ratio of total citations to distinct citing papers', 
        'np cited (ns)':f'number of papers published since 1960 that have been cited at least', # since 1996 for career wide!
        'self%':'self-citation percentage', 
        'rank':'rank based on composite score c', 
        'nc':f'total cites', 
        'h':f'h-index',
        'hm':f'hm-index', 
        'nps':'number of single authored papers',
        'ncs':'total cites to single authored papers', 
        'cpsf':'number of single + first authored papers', 
        'ncsf':'total cites to single + first authored papers', 
        'npsfl':'number of single + first + last authored papers', 
        'ncsfl':'total cites to single + first + last authored papers',
        'c':'composite score', 
        'npciting':'number of distinct citing papers', 
        'cprat':'ratio of total citations to distinct citing papers', 
        'np cited':f'number of papers published since 1960 that have been cited at least', # since 1996 for career wide!
        'np_d':f'# papers since 1960 in titles that are discontinued in Scopus', 
        'nc_d':f'total cites since 1996 from titles that are discontinued in Scopus', 
        'sm-subfield-1':'top ranked Science-Metrix category (subfield) for author', 
        'sm-subfield-1-frac':'associated category fraction',
        'sm-subfield-2':'second ranked Science-Metrix category (subfield) for author', 
        'sm-subfield-2-frac':'associated category fraction', 
        'sm-field':'top ranked higher-level Science-Metrix category (field) for author', 
        'sm-field-frac':'associated category fraction',
        'rank sm-subfield-1':'rank of c within category sm-subfield-1', 
        'rank sm-subfield-1 (ns)':'rank of c (ns) within category sm-subfield-1', 
        'sm-subfield-1 count':'total number of authors within category sm-subfield-1'}
    return metric_name_dict[metric]

def get_inst_field_cntry(data, prefix, year):
    inst = data[f'{prefix}_{year}']['inst_name']
    field = data[f'{prefix}_{year}']['sm-field']
    cntry = data[f'{prefix}_{year}']['cntry']
    return {'cntry': cntry, 'field': field, 'inst': inst}


def try_catch_return(names,prefix,ent1,ent2):
    """Group summary vectors for one field or institution name.

    The f'{prefix}_{ent1}' argument is vestigial: it used to name an
    Elasticsearch index ("career_field", "career_inst"). get_es_results reads
    it as a kind now and _requested_kinds ignores anything that is not
    'career' or 'singleyr', so it falls through to both kinds, which is what
    this wants. It is left as-is rather than tidied because get_metric_summary
    passes the same shape to the cntry lookup two lines above.
    """
    results = get_es_results(names,f'{prefix}_{ent1}',ent2)
    data = es_result_pick(results,'data', None)
    if data is None:
        results = get_es_results(names,f'{prefix}_{ent1}',ent2,True)
        data = es_result_pick(results,'data', None)
    return data


def r2dec(value):
    if isinstance(value, str):
        return value  # If it's a string, return it as is
    else:
        try:
            # Try to convert to float and round to 2 decimals
            rounded_value = round(float(value), 2)
            return rounded_value
        except (ValueError, TypeError):
            # If conversion to float fails, or if the value is not numeric, return the original value
            return value

def get_metric_summary(data, prefix, year, metric, stat):
    if stat == 'median':
        idx = 2
    elif stat == 'min':
        idx = 0
    elif stat == 'max':
        idx = 4
    elif stat == 'q1':
        idx = 1
    elif stat == 'q3':
        idx = 3
    names = get_inst_field_cntry(data, prefix, year)
    # Enforce exact match for country

    results_cntry = get_es_results(names['cntry'],f'{prefix}_cntry','cntry',True)
    data_cntry = es_result_pick(results_cntry,'data', None)
    data_field = try_catch_return(names['field'],prefix,'field',"sm-field")
    data_inst = try_catch_return(names['inst'],prefix,'inst',"inst_name")
    own = data[f'{prefix}_{year}'][metric]
    if metric == 'self%':
           own = own*100
    if data_cntry:
       #print(data_cntry.keys())
       ct = data_cntry[f'{prefix}_{year}'][metric][idx]
       if metric == 'self%':
           ct = ct*100
    else:
       ct = 'N/A'
    if data_field:
       fd = data_field[f'{prefix}_{year}'][metric][idx]
       if metric == 'self%':
           fd = fd*100
    else:
       fd = 'N/A'
    if data_inst:
       ins = data_inst[f'{prefix}_{year}'][metric][idx]
       if metric == 'self%':
           ins = ins*100
    else:
       ins = 'N/A'
    return {'own': str(r2dec(own)),'cntry': str(r2dec(ct)), 'field': str(r2dec(fd)), 'inst': str(r2dec(ins))}

def update_yr_options(career):
    """Radio options whose value is the index into yr_convention_map().

    These used to be two hardcoded lists ending at 2021. They are built from
    the editions actually loaded now, so 2022, 2023 and 2024 are selectable.
    The single-year series has no 2018 edition; it keeps its disabled
    placeholder so the button row still lines up with the career one.
    """
    kind = 'career' if career else 'singleyr'
    years = edition_years(kind)
    prefix = 'TO ' if career else 'IN '
    options = []
    for index, year in enumerate(years):
        label = (prefix if index == 0 else '') + str(year)
        options.append({"label": label, "value": index, 'disabled': False})
        if not career and year == 2017 and 2018 not in years:
            options.insert(1, {"label": "2018", 'disabled': True})
    return options

def update_yr_options2(career):
    """The same list, but valued by the year itself, plus the default year.

    pages/home.py uses this form; the default is the most recent edition.
    """
    kind = 'career' if career else 'singleyr'
    years = edition_years(kind)
    prefix = 'TO ' if career else 'IN '
    options = []
    for index, year in enumerate(years):
        label = (prefix if index == 0 else '') + str(year)
        options.append({"label": label, "value": str(year), 'disabled': False})
        if not career and year == 2017 and 2018 not in years:
            options.insert(1, {"label": "2018", "value": '2018',
                               'disabled': True})
    return(options, str(years[-1]) if years else None)
def update_cr_options(avail):
    if avail == 'both':
        return [{"label": "Career", "value": True}, {"label": "Single year", "value": False}]
    elif avail == 'career':
        return [{"label": "Career", "value": True, 'disabled': True}, {"label": "Single year", "value": False, 'disabled': True}]
    elif avail == 'singleyr':
        return [{"label": "Career", "value": True,'disabled': True}, {"label": "Single year", "value": False, 'disabled': True}]

def update_auth_yrs(keys,prefix):
    if prefix == 'career':
        aptx = 'TO '
    else:
        aptx = 'IN '
    opts = []
    it = 1
    for key in keys:
        if key.split('_')[-1] != "log":
            if it == 1:
                opts.append({"label": aptx + key.split('_')[-1], "value": key.split('_')[-1]})
            else:
                opts.append({"label": key.split('_')[-1], "value": key.split('_')[-1]})
            it = it + 1
    return opts
    

# Quickly search a df for an author
def search_df(df,search_str,datatype = 'author'):
	if datatype == 'author':
	    tmp = df[df['authfull'].str.contains(search_str,na = False)]
	    for i in tmp.index:
	        print(f"Author {tmp.loc[i,'authfull']} ranks {tmp.loc[i,'rank (ns)']} (rank {tmp.loc[i,'rank']} with self-citation) out of {df.shape[0]}")
	if datatype == 'country':
	    tmp = df[df['cntry'].str.contains(search_str,na = False)]
	    print(f"{tmp.shape[0]} out of {df.shape[0]} authors come from {search_str}, and rank an average of {int(tmp['rank (ns)'].mean())} ({int(tmp['rank (ns)'].mean())} with self-citation). Their average % self-citation is {int(tmp['self%'].mean()*100)}% relative to a total mean of {int(df['self%'].mean()*100)}%.")
	if datatype == 'institution':
	    tmp = df[df['inst_name'].str.contains(search_str)]
	    print(f"{tmp.shape[0]} out of {df.shape[0]} authors come from {search_str}, and rank an average of {int(tmp['rank (ns)'].mean())} ({int(tmp['rank (ns)'].mean())} with self-citation). Their average % self-citation is {int(tmp['self%'].mean()*100)}% relative to a total mean of {int(df['self%'].mean()*100)}%.")

# standardize columns across datasest versions (1,2,3,5) and types (single year, career)
def standardize_col_names(df, year, v1_present = False, singleyr = False):
    generic_cols = ['authfull', 'inst_name', 'cntry', 'np', 'firstyr', 'lastyr','rank (ns)', 'nc (ns)', 'h (ns)', 'hm (ns)', 'nps (ns)','ncs (ns)', 'cpsf (ns)', 
                  'ncsf (ns)', 'npsfl (ns)', 'ncsfl (ns)','c (ns)', 'npciting (ns)', 'cprat (ns)', 'np cited (ns)','self%', 'rank', 'nc', 'h', 'hm', 
                  'nps', 'ncs', 'cpsf', 'ncsf','npsfl', 'ncsfl', 'c', 'npciting', 'cprat', 'np cited','np_d', 'nc_d', 'sm-subfield-1', 'sm-subfield-1-frac',
                  'sm-subfield-2', 'sm-subfield-2-frac', 'sm-field', 'sm-field-frac','rank sm-subfield-1', 'rank sm-subfield-1 (ns)', 'sm-subfield-1 count']
    generic_cols_text = [f'author name',f'institution name (large institutions only)',f'country associated with most recent institution',f'number of papers from 1960 to {year})',
                       f'year of first publication',f'year of most recent publication',f'rank based on composite score c',f'total cites from 1996 to {year}',
                       f'h-index as of the end of {year}',f'hm-index as of end-{year}',f'number of single authored papers',f'total cites to single authored papers',
                       f'number of single + first authored papers',f'total cites to single + first authored papers',f'number of single + first + last authored papers',
                       f'total cites to single + first + last authored papers',f'composite score',f'number of distinct citing papers',
                       f'ratio of total citations to distinct citing papers',f'number of papers 1960-{year} that have been cited at least once (1996-{year})',
                       f'self-citation percentage',f'rank based on composite score c',f'total cites 1996-{year}',f'h-index as of end-{year}',
                       f'hm-index as of end-{year}',f'number of single authored papers',f'total cites to single authored papers',
                       f'number of single + first authored papers',f'total cites to single + first authored papers',f'number of single + first + last authored papers',
                       f'total cites to single + first + last authored papers',f'composite score',f'number of distinct citing papers',
                       f'ratio of total citations to distinct citing papers',f'number of papers 1960-{year} that have been cited at least once (1996-{year})',
                       f'# papers 1960-{year} in titles that are discontinued in Scopus',f'total cites 1996-{year} from titles that are discontinued in Scopus',
                       f'top ranked Science-Metrix category (subfield) for author',f'associated category fraction',f'second ranked Science-Metrix category (subfield) for author',
                       f'associated category fraction',f'top ranked higher-level Science-Metrix category (field) for author',
                       f'associated category fraction',f'rank of c within category sm-subfield-1',f'rank of c (ns) within category sm-subfield-1',
                       f'total number of authors within category sm-subfield-1']
    if not v1_present: 
        df.columns = generic_cols
        return(df,dict(zip(generic_cols, generic_cols_text))) # len(generic_cols_text) = 46
    else:
        remove_cols = ['np cited (ns)','np cited','np_d','nc_d','rank sm-subfield-1','rank sm-subfield-1 (ns)','sm-subfield-1 count']
        remove_text = [f'number of papers 1960-{year} that have been cited at least once (1996-{year})',f'number of papers 1960-{year} that have been cited at least once (1996-{year})',f'# papers 1960-{year} in titles that are discontinued in Scopus',f'total cites 1996-{year} from titles that are discontinued in Scopus',f'rank of c within category sm-subfield-1',f'rank of c (ns) within category sm-subfield-1',f'total number of authors within category sm-subfield-1']

        if year == 2017 or year == 2018:
            df = df.drop(columns = ['sm-1', 'sm-2','sm22'])
            if singleyr and year == 2017: # singleyr 2017 missing 2 columns!
                remove_cols += 'firstyr','lastyr' 
                remove_text += f'year of first publication',f'year of most recent publication'
            for item in remove_cols: generic_cols.remove(item)
            for item in remove_text: generic_cols_text.remove(item)
            df.columns = generic_cols
        else:
            df.columns = generic_cols
            for item in remove_cols: generic_cols.remove(item)
            for item in remove_text: generic_cols_text.remove(item)
            df = df.drop(columns = remove_cols)
        return(df,dict(zip(generic_cols, generic_cols_text))) # len(generic_cols_text) = 39 (37 for singleyr 2017)

def gen_dist_from_summary(sum_vec, N):
    data_size = N
    data = np.concatenate([
        np.random.uniform(sum_vec[0], sum_vec[1], data_size // 4),
        np.random.uniform(sum_vec[1], sum_vec[2], data_size // 4),
        np.random.uniform(sum_vec[2], sum_vec[3], data_size // 4),
        np.random.uniform(sum_vec[3], sum_vec[4], data_size // 4)
    ])
    return data


def get_violin_compare(fig, in1,in2,color1,color2,name,group_num):
    # The last entry is number of samples
    N1 = in1[5]
    N2 = in2[5]
    data1 = gen_dist_from_summary(in1, N1)
    data2 = gen_dist_from_summary(in2, N2)
    if N1>N2:
        N1 = int(10*(N1/N2))
        if N1>50:
            N1 = 50
        N2 = 10
    elif N2>N1:
        N2 = int(10*(N2/N1))
        if N2>50:
            N2 = 50
        N1 = 10
    fig.add_trace(go.Violin(
        y=data1,
        box_visible=False,
        fillcolor=color1[0],
        #fillcolor='rgba(0, 255, 0, 0.5)',
        side='positive',
        hoverinfo='text+y',
        #legendgroup='M',
        name = name
    ), row = 1, col = group_num)
    fig.add_trace(go.Violin(
        y=data2,
        box_visible=False,
        fillcolor=color2[0],
        side='negative',
        hoverinfo='text+y',
        #legendgroup='M',
        name = name
    ), row = 1, col = group_num)
    # Update layout for better visibility
    fig.update_traces(meanline_visible=True,
                      points= False, # show all points
                      jitter=0.05,  # add some jitter on points for better visibility
                      scalemode='width'
                     )
    fig.update_layout(violingap=0, violinmode='overlay', showlegend=False)
    
    # Show the plot
    return fig

def get_world_df(year,sts,prefix):
    #print(prefix)
    if sts == 'median':
        st_idx = 2
    elif sts == 'min':
        st_idx = 0
    elif sts == 'max':
        st_idx = 4
    elif sts == '25':
        st_idx = 1
    elif sts == '75':
        st_idx = 3
    # The country summaries used to come from aggregate/cntry_{prefix}.pkl,
    # which only ever held 2017 to 2021. Reading group_metrics instead is what
    # makes the world map work for 2022, 2023 and 2024; without it the map
    # rendered every country as 0 for those years, because the lookup below
    # raised KeyError and fell into the except branch.
    metrics = ['h', 'nc', 'hm',  'ncs', 'ncsf', 'ncsfl', 'c']
    metrics_name = ['H-index', '# citations', 'Hm-index',  '# citations to single auth papers', '# citations to single/first auth papers', '# citations to single/first/last auth papers', 'Composite (c) score']
    rows = _fetch(
        'select group_value, metric, min, q1, median, q3, max '
        'from group_metrics '
        'where group_kind = %s and edition_id = %s and metric = any(%s)',
        ('cntry', f'{prefix}-{year}', metrics))
    summary = {(group_value, metric): [mn, q1, median, q3, mx]
               for group_value, metric, mn, q1, median, q3, mx in rows}
    codes = sorted({group_value for group_value, _ in summary})
    df = pd.DataFrame(columns=['code', 'country', sts, 'geometry', 'metric', 'metric_name'])
    kk = 0
    for idxx, metric in enumerate(metrics):
        for code in codes:
            # Four codes in the data are defunct states that
            # country_converter cannot resolve: csk (Czechoslovakia), scg
            # (Serbia and Montenegro), sux (the Soviet Union) and ant (the
            # Netherlands Antilles). This function used to hand three of them
            # a name anyway, and two of those names were simply a different
            # country: scg was drawn as the Czech Republic and ant as the
            # Netherlands. Labelling a country as another country is worse
            # than leaving it off the map, and there is nothing correct to
            # put there either, since none of the four is a country plotly
            # can draw today. So all four are excluded, which is also what
            # the group dropdowns do with them (_country_full_name).
            cur_name = _country_full_name(code) if code != 'nan' else None
            if cur_name is not None:
                vector = summary.get((code, metric))
                if vector is not None and vector[st_idx] is not None:
                    df.loc[kk] = ([code.upper()]) + [cur_name] + [vector[st_idx]]  + [''] + [str(metric)] + [str(metrics_name[idxx])]
                else:
                    df.loc[kk] = ([code.upper()]) + [cur_name] + [0] + [''] + [str(metric)] + ['lel']
                kk = kk +1
    return df