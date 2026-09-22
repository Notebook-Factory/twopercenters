import numpy as np
import pandas as pd

import plotly.graph_objects as go
from IPython.core.display import display, HTML
from plotly.offline import plot
import plotly.express as px
import plotly.colors
from plotly.subplots import make_subplots
import country_converter as coco

from citations_lib.controls import kind_options
import os
import json
import re
import urllib.parse
import urllib.request
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

# The four codes in the data that country_converter has no name for, because
# the states they name no longer exist: Czechoslovakia, Serbia and
# Montenegro, the Soviet Union and the Netherlands Antilles. Asking about
# them is what printed
#
#     sux not found in ISO3
#     ant not found in ISO3
#     csk not found in ISO3
#     scg not found in ISO3
#
# four times over every time the app started, once per conversion path. The
# answer is known and is already handled everywhere it matters, so they are
# not asked about. A code that turns up here later and cannot be resolved
# still says so, which is the part of that warning worth keeping.
_DEFUNCT_CODES = frozenset({'csk', 'scg', 'sux', 'ant'})


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
        if str(code).lower() in _DEFUNCT_CODES:
            _COUNTRY_NAMES[code] = None
        else:
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


# ---------------------------------------------------------------------------
# Model estimates.
#
# These read the `predictions` and `prediction_runs` tables, written offline
# by rdl/publish.py. Nothing here imports torch or anything under rdl/: the
# web process must stay small, and tests/test_no_torch_in_app.py enforces it.
#
# Every helper distinguishes a measured value from an estimated one, because
# the page that shows them must never present the two alike.
# ---------------------------------------------------------------------------

# The bands the coverage chart reports. Narrow where the list is dense and
# wide where it thins out, so the shape of the decay is visible rather than
# being flattened into one long tail.
_RANK_BANDS = [
    (1, 25_000), (25_001, 50_000), (50_001, 75_000), (75_001, 100_000),
    (100_001, 150_000), (150_001, 200_000), (200_001, 300_000),
    (300_001, 500_000), (500_001, 1_000_000), (1_000_001, 3_000_000),
]

# Where the published list stops being everybody. Verified across all eight
# career editions: every rank from 1 to 100,000 appears, and past it coverage
# falls away. career-2018 is the one exception at 99,998 of 100,000.
RANK_CUTOFF = 100_000


def rank_coverage(kind, year):
    """How much of each rank band actually appears in one edition.

    `rank` is a position in a ranking of every scientist scored, not of the
    people published, so a reader meeting a rank of 214,011 beside a list of
    159,683 has no way to make sense of it. This is the shape that explains
    it: the list holds every one of the first 100,000 ranks and then thins
    out, because past that point a researcher only appears if they are near
    the top of their own subfield.

    Returns one dict per band with the band's bounds, how many of its ranks
    are present, how wide it is, and the resulting share. Bands entirely past
    the edition's largest rank are dropped rather than drawn as empty.
    """
    table = _TABLE_BY_KIND.get(kind)
    if table is None:
        return []
    edition_id = f'{kind}-{year}'

    rows = _fetch(
        f"select count(*), min(rank), max(rank) from {table} "
        "where edition_id = %s and rank is not null", (edition_id,))
    if not rows or not rows[0][0]:
        return []
    published, _lowest, highest = rows[0]

    cases = " ".join(
        f"count(*) filter (where rank between {lo} and {hi}) as b{index},"
        for index, (lo, hi) in enumerate(_RANK_BANDS)).rstrip(",")
    counts = _fetch(
        f"select {cases} from {table} "
        "where edition_id = %s and rank is not null", (edition_id,))[0]

    bands = []
    for (lo, hi), present in zip(_RANK_BANDS, counts):
        if lo > highest:
            break
        width = min(hi, int(highest)) - lo + 1
        if width <= 0:
            continue
        bands.append({
            'low': lo, 'high': min(hi, int(highest)),
            'present': int(present), 'width': width,
            'share': int(present) / width,
        })
    return {
        'edition_id': edition_id, 'published': int(published),
        'highest_rank': int(highest), 'bands': bands,
    }


def prediction_run(task):
    """What a published model run scored, or None if nothing is published."""
    rows = _fetch(
        "select task_type, metrics, baseline, epochs, trained_at, "
        "       graph_variant, notes "
        "from prediction_runs where task = %s", (task,))
    if not rows:
        return None
    task_type, metrics, baseline, epochs, trained_at, variant, notes = rows[0]
    return {'task': task, 'task_type': task_type, 'metrics': metrics,
            'baseline': baseline, 'epochs': epochs, 'trained_at': trained_at,
            'graph_variant': variant, 'notes': notes}


def retraction_by_edition(task):
    """Share of researchers with any retraction exposure, per data year.

    Measured years come from career_metrics.nc_rw, which the publishers
    recorded. Estimated years come from the predictions table. `measured`
    says which, and nothing downstream may drop it.
    """
    measured = _fetch(
        "select e.data_year, "
        "       avg(case when m.nc_rw > 0 then 1.0 else 0.0 end) "
        "from career_metrics m join editions e using (edition_id) "
        "where m.nc_rw is not null group by e.data_year")
    estimated = _fetch(
        "select e.data_year, "
        "       avg(case when p.probability > 0.5 then 1.0 else 0.0 end) "
        "from predictions p join editions e using (edition_id) "
        "where p.task = %s group by e.data_year", (task,))
    rows = ([{'data_year': int(y), 'share': float(v), 'measured': True}
             for y, v in measured]
            + [{'data_year': int(y), 'share': float(v), 'measured': False}
               for y, v in estimated])
    return sorted(rows, key=lambda r: r['data_year'])


def retraction_counts_by_edition(task='retraction_exposure'):
    """Mean citations from retracted papers per researcher, per data year.

    The companion to retraction_by_edition, which reports how many
    researchers have any. This reports how many citations are involved, which
    is the quantity a reader asks for next.

    Measured years come from career_metrics.nc_rw; estimated years from the
    regression's published output. `measured` says which, and the step
    between the two at the tracking boundary is the regression being
    conservative rather than a real jump. Anything drawing this has to say
    so.
    """
    measured = _fetch(
        "select e.data_year, avg(m.nc_rw) "
        "from career_metrics m join editions e using (edition_id) "
        "where m.nc_rw is not null group by e.data_year")
    estimated = _fetch(
        "select e.data_year, avg(p.value) "
        "from predictions p join editions e using (edition_id) "
        "where p.task = %s group by e.data_year", (task,))
    rows = ([{'data_year': int(y), 'mean': float(v), 'measured': True}
             for y, v in measured]
            + [{'data_year': int(y), 'mean': float(v), 'measured': False}
               for y, v in estimated])
    return sorted(rows, key=lambda r: r['data_year'])


def retraction_for_author(authfull, task):
    """One researcher's exposure across every career edition.

    Resolved through author_id, not through the raw name string. The name a
    researcher is published under changes: John Ioannidis appears as
    "Ioannidis, John P.A." in seven editions and "Ioannidis, John Pa" in
    2022, and matching the string directly silently dropped that year from
    his history. Identity resolution exists precisely so this does not have
    to happen twice.

    A display name can still belong to more than one person, so every
    matching author is included and the most exposed reading is reported per
    year rather than one being chosen silently.
    """
    author_ids = [row[0] for row in _fetch(
        "select author_id from authors where authfull_display = %s",
        (authfull,))]
    if not author_ids:
        return []

    # The recorded years carry a magnitude as well as a yes/no, and the
    # magnitude is what a reader actually wants: `nc_rw` is a count of
    # citations that arrived from papers later retracted, and its share of
    # the author's total citations says how much of their record rests on
    # withdrawn work. That share is small for almost everyone (mean 0.058%
    # across career-2024, maximum 15%), which is why it is reported as text
    # rather than as a bar height: drawn to scale beside a likelihood it
    # would be invisible, and the two are not the same quantity anyway.
    measured = _fetch(
        "select e.data_year, "
        "       max(case when m.nc_rw > 0 then 1 else 0 end), "
        "       max(m.nc_rw), "
        "       max(100.0 * m.nc_rw / nullif(m.nc, 0)) "
        "from career_metrics m join editions e using (edition_id) "
        "where m.author_id = any(%s) and m.nc_rw is not null "
        "group by e.data_year", (author_ids,))
    # Two models answer two different questions about the same untracked
    # years, and the page shows both: `task` gives the likelihood of any
    # exposure at all, and retraction_exposure estimates how many citations
    # were involved. The magnitude is the weaker of the two and is reported
    # with its error rather than as a bare number.
    estimated = _fetch(
        "select e.data_year, max(p.probability), max(q.value) "
        "from predictions p "
        "join editions e using (edition_id) "
        "left join predictions q "
        "  on q.metric_id = p.metric_id "
        " and q.task = 'retraction_exposure' "
        "where p.author_id = any(%s) and p.task = %s "
        "group by e.data_year", (author_ids, task))
    rows = ([{'data_year': int(y), 'value': float(v), 'measured': True,
              'citations': int(count or 0),
              'share': float(share) if share is not None else None}
             for y, v, count, share in measured]
            + [{'data_year': int(y), 'value': float(v), 'measured': False,
                'citations': round(float(c)) if c is not None else None,
                'share': None}
               for y, v, c in estimated])
    return sorted(rows, key=lambda r: r['data_year'])


def author_options(result):
    """Dropdown options that show WHO each candidate is, not just a name.

    `Zhu, Jianguo` is one string shared by dozens of real researchers, and a
    list of bare names gives a reader no way to tell which one they are
    about to select. Each option carries the institution and country, so the
    choice is informed, and when one name covers several researchers in the
    same result the option says so rather than silently standing for one of
    them.

    The value stays the name, because that is what every downstream callback
    still looks an author up by. Narrowing between two people with the same
    name is done by typing an affiliation into the search, which
    get_es_results now understands; making the value an author_id is the
    deeper change that would let the dropdown itself do it.
    """
    if result is None or len(result) == 0:
        return []

    def _cell(row, column):
        value = row.get(column)
        if value is None or (isinstance(value, float) and value != value):
            return None
        text = str(value).strip()
        return text or None

    people = {}
    for _index, row in result.iterrows():
        name = _cell(row, '_source.authfull')
        if not name:
            continue
        # Count distinct PEOPLE, not distinct institution strings. One
        # researcher's affiliation is recorded differently from one edition
        # to the next often enough to matter: John Ioannidis appears as both
        # "Stanford University School of Medicine" and "Stanford University",
        # and counting strings called him two researchers.
        author = _cell(row, '_source.author_id') or name
        entry = people.setdefault(name, {})
        place = _cell(row, '_source.inst_name')
        country = _cell(row, '_source.cntry')
        if place and country:
            place = f"{place} ({str(country).upper()})"
        elif country:
            place = str(country).upper()
        if place and not entry.get(author):
            entry[author] = place
        else:
            entry.setdefault(author, place)

    options = []
    for name, by_author in people.items():
        places = [p for p in by_author.values() if p]
        if len(by_author) > 1:
            shown = ", ".join(places[:2])
            label = (f"{name} - {len(by_author)} researchers"
                     + (f": {shown}" if shown else "")
                     + (", ..." if len(places) > 2 else ""))
        elif places:
            label = f"{name} - {places[0]}"
        else:
            label = name
        options.append({"label": label, "value": name})
    return options


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


def country_researcher_count(country, kind, year):
    """How many researchers one country contributes to one edition."""
    if kind not in _TABLE_BY_KIND:
        return 0
    code = str(coco.convert(names=country, to='ISO3')).lower()
    rows = _fetch(f'select count(*) from {_TABLE_BY_KIND[kind]} '
                  f'where country_code = %s and edition_id = %s',
                  (code, f'{kind}-{year}'))
    return rows[0][0] if rows else 0


def country_researchers(country, kind, year, limit=None):
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

    `limit` caps the rows returned. The United States contributes 87,859
    researchers to career-2024; handing all of them to a DataTable made a
    7.2 MB response that the browser then had to parse and render, which is
    why clicking the biggest countries looked like nothing happening. The
    caller asks for a page's worth and reports the true total separately.
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
        f'order by a.authfull_display'
        + (' limit %s' if limit else ''),
        (code, f'{kind}-{year}') + ((limit,) if limit else ()))
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
        # Two clauses, either of which can satisfy the search.
        #
        # The first is the original fuzzy name match, unchanged, and it is
        # boosted so a plain name search ranks exactly as it did before.
        #
        # The second lets the terms of one query land in different fields, so
        # "zhu jianguo stanford" finds the Zhu Jianguo at Stanford rather
        # than nothing. That matters here more than it would elsewhere:
        # `Zhu, Jianguo` is one name shared by dozens of real people, and a
        # name alone cannot separate them. cross_fields does not support
        # fuzziness, which is why it supplements the fuzzy clause instead of
        # replacing it: misspell the name and the first clause still catches
        # it, add an affiliation and the second does.
        name_fields = search_fields if isinstance(search_fields, list) \
            else [search_fields]
        query = {
            "bool": {
                "should": [
                    {"multi_match": {
                        "query": search_term,
                        "operator": "and",
                        "fuzziness": "auto",
                        "fields": name_fields,
                        "boost": 3.0,
                    }},
                    {"multi_match": {
                        "query": search_term,
                        "type": "cross_fields",
                        "operator": "and",
                        "fields": name_fields + ["inst_name", "cntry",
                                                 "sm_field"],
                    }},
                ],
                "minimum_should_match": 1,
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
def update_cr_options(avail, radio_id):
    """The dataset options for one author's picker.

    Both halves are disabled when the author has only one of the two
    records, which locks the choice to the one that exists.

    It takes the radio's id because the options carry the label ids that the
    icons and their tooltips hang on. Written out here as the words "Career"
    and "Single year", this callback used to undo the icons the moment an
    author was chosen.
    """
    return kind_options(radio_id, disabled=avail != 'both')

def update_auth_yrs(keys, prefix):
    """Year options for one author: every edition, unavailable ones disabled.

    This used to emit only the years the author actually has, so a researcher
    present in 2024 alone got a single button and the rest of the row simply
    vanished. That hides the shape of the data: the reader cannot tell whether
    a year is missing for this person or missing from the dashboard. Every
    edition of the kind is listed now, and the ones this author has no row in
    are disabled, so the gap is visible and unclickable.
    """
    prefix_label = 'TO ' if prefix == 'career' else 'IN '
    available = {str(key).split('_')[-1]
                 for key in keys if str(key).split('_')[-1] != 'log'}

    options = []
    for index, year in enumerate(edition_years(prefix)):
        year = str(year)
        label = (prefix_label if index == 0 else '') + year
        options.append({'label': label, 'value': year,
                        'disabled': year not in available})
    return options


def first_available_year(options):
    """The earliest year an author has data for, from update_auth_yrs output.

    The year row is in ascending edition order, so the first option that is
    not disabled is the earliest one this author appears in. Selecting it
    rather than options[0] matters because options[0] is now always the
    oldest edition, which for most authors is a year they have no data in.
    """
    for option in options or []:
        if not option.get('disabled'):
            return option['value']
    return None


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

# The tables the model reads, in the order the graph joins them. Kept here
# rather than imported from rdl/spec.py because the web process must never
# import anything that pulls in torch.
GRAPH_TABLES = ('career_metrics', 'authors', 'editions', 'institutions',
                'countries', 'fields', 'subfields')


def graph_table_sizes():
    """How many rows each table in the training graph holds.

    The schema picture on the predictions page is drawn from the live
    database rather than from a caption someone has to remember to update,
    so a node whose table grows gets bigger on its own.
    """
    parts = ' union all '.join(
        f"select '{name}' as t, count(*) from {name}"
        for name in GRAPH_TABLES)
    return {name: int(count) for name, count in _fetch(parts)}


def prediction_coverage(task):
    """How many estimates one published run put in the database.

    Returns the row count, how many researchers they cover, and which data
    years, because the honest sentence about a set of estimates names all
    three.
    """
    rows = _fetch(
        "select count(*), count(distinct p.author_id), "
        "       min(e.data_year), max(e.data_year), "
        "       count(distinct p.edition_id) "
        "from predictions p join editions e using (edition_id) "
        "where p.task = %s", (task,))
    if not rows or not rows[0][0]:
        return None
    total, authors, first_year, last_year, editions = rows[0]
    return {'rows': int(total), 'authors': int(authors),
            'first_year': int(first_year), 'last_year': int(last_year),
            'editions': int(editions)}


# ---------------------------------------------------------------------------
# The composite score, recomputed
# ---------------------------------------------------------------------------
#
# The published `c` is not an opaque number. It is the sum of six
# log-transformed ratios, each indicator against the largest value of that
# indicator in the same edition:
#
#   c = ln(nc+1)/ln(nc_max+1) + ln(h+1)/ln(h_max+1) + ln(hm+1)/ln(hm_max+1)
#     + ln(ncs+1)/ln(ncs_max+1) + ln(ncsf+1)/ln(ncsf_max+1)
#     + ln(ncsfl+1)/ln(ncsfl_max+1)
#
# This was checked against every published row rather than taken on faith.
# Recomputing `c` from the six columns and the maxima in metric_maxima
# reproduces the published value with a maximum absolute error of 0.0 across
# career-2019 through career-2024, and 5e-7 in career-2017, which is the
# rounding in the source file.
#
# career-2018 is the exception: all 105,000 of its rows disagree, by up to
# 0.228. Whatever maxima that edition's scores were computed with are not the
# ones recorded for it, and the same holds for its self-citation-excluded
# score. So the calculator refuses that edition rather than showing a reader
# a score that will not match the one printed beside it.

COMPOSITE_METRICS = ('nc', 'h', 'hm', 'ncs', 'ncsf', 'ncsfl')

# Every other edition of both kinds reproduces exactly, career and
# single-year alike, which was checked the same way over all 2.7 million
# rows.
_COMPOSITE_BROKEN = {('career', 2018)}


def composite_is_reproducible(kind, year):
    """Whether this edition's published score can be recomputed from its
    parts. False only for career-2018, where the recorded maxima are not the
    ones the published scores were computed with."""
    return (kind, int(year)) not in _COMPOSITE_BROKEN


def composite_maxima(kind, year, ns=False):
    """The six per-edition maxima the composite score divides by."""
    suffix = '_ns' if ns else ''
    wanted = [f'{metric}{suffix}' for metric in COMPOSITE_METRICS]
    rows = _fetch(
        "select metric, max_value from metric_maxima "
        "where edition_id = %s and metric = any(%s)",
        (f'{kind}-{year}', wanted))
    found = {metric: float(value) for metric, value in rows}
    return {metric: found[f'{metric}{suffix}'] for metric in COMPOSITE_METRICS
            if f'{metric}{suffix}' in found}


def composite_score(values, maxima):
    """Sum the six log ratios. Returns None if any input is missing."""
    import math
    total = 0.0
    for metric in COMPOSITE_METRICS:
        value = values.get(metric)
        ceiling = maxima.get(metric)
        if value is None or not ceiling:
            return None
        total += math.log(max(float(value), 0.0) + 1) / math.log(ceiling + 1)
    return total


def score_standing(kind, year, score, ns=False):
    """Where a composite score would sit in one published edition.

    Two numbers, because they answer different questions and the dashboard
    used to conflate them. `within_list` is the position among the people
    actually published in that edition, which is what a reader means by "what
    number am I". `scopus_rank` is the rank Scopus assigned, and it counts
    everyone the publishers scored rather than only the ones who made the cut.

    Both are read off the researcher this score lands beside, in one index
    lookup. Counting the rows above the score answers the same question and
    took 30 ms; the what-if calculator asks on every keystroke.
    """
    table = _TABLE_BY_KIND.get(kind)
    if table is None or score is None:
        return None
    suffix = '_ns' if ns else ''
    edition_id = f'{kind}-{year}'
    published = edition_size(kind, year)

    # The highest-scoring researcher this score does not beat. Displacing them
    # means taking their position on the list.
    neighbour = _fetch(
        f"select rank{suffix}, list_position{suffix} from {table} "
        f"where edition_id = %s and c{suffix} <= %s "
        f"order by c{suffix} desc limit 1", (edition_id, score))
    if not neighbour or neighbour[0][1] is None:
        # Either the score beats everyone published, or this edition's
        # positions were never filled (pipeline/list_position.py). Counting is
        # slower but always right, so it is the fallback rather than the
        # answer.
        rows = _fetch(
            f"select count(*) from {table} "
            f"where edition_id = %s and c{suffix} > %s", (edition_id, score))
        ahead = int(rows[0][0])
        rank_rows = _fetch(
            f"select rank{suffix} from {table} "
            f"where edition_id = %s and c{suffix} <= %s "
            f"and rank{suffix} is not null "
            f"order by c{suffix} desc limit 1", (edition_id, score))
        return {'within_list': ahead + 1,
                'scopus_rank': int(rank_rows[0][0]) if rank_rows else 1,
                'published': published}

    scopus_rank, position = neighbour[0]
    return {'within_list': int(position),
            'scopus_rank': int(scopus_rank) if scopus_rank else None,
            'published': published}


def edition_size(kind, year):
    """How many researchers one edition published."""
    return edition_sizes(kind).get(f'{kind}-{year}')


# Edition sizes change only when a new edition is loaded, and counting them
# is a full scan of 1.4 million rows. Counted once per process.
_EDITION_SIZES: dict[str, dict[str, int]] = {}


def edition_sizes(kind):
    """{edition_id: published rows} for one kind, counted once per process."""
    table = _TABLE_BY_KIND.get(kind)
    if table is None:
        return {}
    if kind not in _EDITION_SIZES:
        # Read off the edition, not counted. Counting is a sequential scan of
        # 1.4 million rows; pipeline/list_position.py records the figure when
        # it walks each edition. An edition it has not reached yet is counted
        # once here rather than left out.
        sizes = {}
        for edition_id, published in _fetch(
                "select edition_id, published_rows from editions "
                "where kind = %s", (kind,)):
            if published is None:
                published = _fetch(
                    f"select count(*) from {table} where edition_id = %s",
                    (edition_id,))[0][0]
            sizes[edition_id] = int(published)
        _EDITION_SIZES[kind] = sizes
    return _EDITION_SIZES[kind]


# ---------------------------------------------------------------------------
# The top of a list
# ---------------------------------------------------------------------------

@lru_cache(maxsize=512)
def iso2(country_code):
    """The two-letter code for a three-letter one, for flag images.

    The fact tables carry ISO3, which is what the published data uses, and
    every flag service is keyed on ISO2. Cached because the conversion is
    about 3 ms a call and the same handful of countries come up over and
    over.
    """
    if not country_code:
        return ''
    code = str(coco.convert(names=str(country_code), to='ISO2'))
    return '' if code.lower() == 'not found' else code.lower()


def top_researchers(kind, year, metric, ns=False, limit=10,
                    _force_live=False):
    """The highest `limit` researchers by one metric in one edition.

    Reads the ordering that pipeline/build_relational.py precomputed, and
    joins the fact row for everything else, so the institution, the field,
    the rank and the list position are read from the one place they are
    maintained rather than from a copy.

    If that table holds nothing for this edition, because migration 012 has
    been applied but the pipeline has not run since, this asks the fact table
    directly instead. A tab that is slow until the next build beats a tab
    that is empty, and the two paths agree: the ordering here is the ordering
    the fill uses, ties included.

    `_force_live` exists so the test suite can compare the two paths against
    each other. Nothing in the dashboard passes it.
    """
    table = _TABLE_BY_KIND.get(kind)
    if table is None:
        return []
    edition_id = f'{kind}-{year}'
    suffix = '_ns' if ns else ''
    rows = []
    if not _force_live:
        rows = _fetch(
            f'select t.position, t.author_id, a.authfull_display, i.inst_name, '
            f'm.country_code, f.name, t.value, m.rank{suffix}, '
            f'm.list_position{suffix}, m.self_pct '
            f'from top_researchers t '
            f'join {table} m on m.author_id = t.author_id '
            f'   and m.edition_id = t.edition_id '
            f'join authors a on a.author_id = t.author_id '
            f'left join institutions i on i.institution_id = m.institution_id '
            f'left join fields f on f.field_id = m.field_id '
            f'where t.edition_id = %s and t.metric = %s and t.ns = %s '
            f'order by t.position limit %s',
            (edition_id, metric, bool(ns), limit))
    if not rows:
        rows = _fetch(
            f'select row_number() over (order by m.{metric}{suffix} desc, '
            f'   m.author_id), m.author_id, a.authfull_display, i.inst_name, '
            f'm.country_code, f.name, m.{metric}{suffix}, m.rank{suffix}, '
            f'm.list_position{suffix}, m.self_pct '
            f'from {table} m '
            f'join authors a on a.author_id = m.author_id '
            f'left join institutions i on i.institution_id = m.institution_id '
            f'left join fields f on f.field_id = m.field_id '
            f'where m.edition_id = %s and m.{metric}{suffix} is not null '
            f'order by m.{metric}{suffix} desc, m.author_id limit %s',
            (edition_id, limit))
    return [{'position': int(position), 'author_id': author_id,
             'name': name, 'institute': inst or '',
             'country_code': (country or '').upper(),
             'flag': iso2(country), 'field': field or '',
             'value': float(value),
             'self_pct': None if self_pct is None else float(self_pct),
             'rank': int(rank) if rank is not None else None,
             'list_position': int(listpos) if listpos is not None else None}
            for (position, author_id, name, inst, country, field, value,
                 rank, listpos, self_pct) in rows]


# The columns the Top 10 card reads off a fact row, published and
# self-citation-excluded. `np` and `self_pct` have no excluded variant: the
# paper count is the same either way, and the self-citation share is the
# thing being excluded.
_CARD_COLUMNS = ('c', 'h', 'hm', 'nc', 'ncs', 'ncsf', 'ncsfl',
                 'rank', 'list_position', 'rank_subfield')
_CARD_PLAIN_ONLY = ('np', 'self_pct', 'subfield_count')


def author_metrics(author_id, kind, year):
    """One researcher's fact row, by id, for the Top 10 tab's card.

    The Explore tab reaches its researcher through Elasticsearch because it
    starts from a name somebody typed. This tab starts from an id it already
    holds, so it asks Postgres for the row it has the key to, which is
    shorter and is one fewer service in the path of a click.
    """
    table = _TABLE_BY_KIND.get(kind)
    if table is None:
        return None
    columns = (list(_CARD_COLUMNS) + [f'{name}_ns' for name in _CARD_COLUMNS]
               + list(_CARD_PLAIN_ONLY))
    selected = ', '.join(f'm.{name}' for name in columns)
    rows = _fetch(
        f'select a.authfull_display, i.inst_name, m.country_code, f.name, '
        f's.name, {selected} '
        f'from {table} m '
        f'join authors a on a.author_id = m.author_id '
        f'left join institutions i on i.institution_id = m.institution_id '
        f'left join fields f on f.field_id = m.field_id '
        f'left join subfields s on s.subfield_id = m.subfield_1_id '
        f'where m.author_id = %s and m.edition_id = %s',
        (author_id, f'{kind}-{year}'))
    if not rows:
        return None
    row = rows[0]
    data = {'author_id': author_id, 'name': row[0], 'institute': row[1] or '',
            'country_code': (row[2] or '').upper(), 'field': row[3] or '',
            'subfield': row[4] or ''}
    for name, value in zip(columns, row[5:]):
        data[name] = None if value is None else float(value)
    return data


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------
#
# The dashboard reports what the published list says and stops there. A reader
# who wants the papers behind a number has to go and find the person
# themselves, and the name on the card is the only thing they have to go on.
#
# OpenAlex has an open API, no key, that resolves a name to a canonical author
# id. What it cannot do is tell us the match is the right person: a search for
# a common surname returns the most cited match, not the one on this card. So
# the match is only accepted when the names agree once punctuation, case,
# order and initials are put aside, and the card shows no link at all when
# they do not. A missing link is a small loss. A link to the wrong researcher
# is a claim this dashboard has no business making.

_OPENALEX_SEARCH = 'https://api.openalex.org/authors?per-page=5&search='


def _name_key(name):
    """A name reduced to what two spellings of it have in common.

    "Ioannidis, John P.A." and "John P. A. Ioannidis" are the same person
    written two ways: surname first or last, initials spaced or not. This
    reduces both to the surname plus the first letters of everything else, so
    they compare equal without treating every J. Smith as the same person.
    """
    cleaned = re.sub(r'[^a-z ]', ' ', str(name or '').lower())
    parts = [p for p in cleaned.split() if p]
    if not parts:
        return ''
    longest = max(parts, key=len)
    initials = sorted(p[0] for p in parts if p is not longest)
    return longest + '|' + ''.join(initials)


@lru_cache(maxsize=2048)
def openalex_author(name, timeout=2.5):
    """The OpenAlex page for this researcher, or None if it cannot be sure.

    Cached per process: the same author is looked up again on every change of
    year or of the self-citation toggle, and this is a call to somebody
    else's server. Any failure, including a slow one, returns None rather
    than raising: a link is an extra, and the card has to render without it.
    """
    if not name:
        return None
    wanted = _name_key(name)
    if not wanted:
        return None
    try:
        with urllib.request.urlopen(
                _OPENALEX_SEARCH + urllib.parse.quote(str(name)),
                timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception:
        return None
    for candidate in (payload.get('results') or []):
        if _name_key(candidate.get('display_name')) == wanted:
            url = candidate.get('id')
            return url if isinstance(url, str) and url.startswith('http') else None
    return None


# ---------------------------------------------------------------------------
# The map
# ---------------------------------------------------------------------------

@lru_cache(maxsize=32)
def city_points(kind, year, limit_institutes=4):
    """Every place the selected edition's researchers work, with what is
    there.

    One row per city, keyed on the coordinates ROR gives rather than on the
    name: there are eleven Springfields in the United States, and two cities
    of one name in one country are two places.

    All three measures come back together rather than one per request. The
    query takes about half a second, the payload is a few hundred kilobytes,
    and a reader switching between researchers, citations and papers is
    asking the same question of the same rows, so the switch belongs in the
    browser rather than in another round trip.

    Researchers whose institution could not be located are not here. That is
    most institution names and a minority of researchers: see
    pipeline/ror_match.py for the measured coverage.
    """
    table = _TABLE_BY_KIND.get(kind)
    if table is None:
        return []
    rows = _fetch(
        f'select r.city, max(r.region) as region, r.country_code, '
        f'r.lat, r.lng, '
        f'count(*) as researchers, sum(m.nc) as citations, '
        f'sum(m.np) as papers, max(m.h) as h, '
        f'(array_agg(i.inst_name order by m.nc desc nulls last))[1:%s] '
        f'from {table} m '
        f'join institution_ror r on r.institution_id = m.institution_id '
        f'join institutions i on i.institution_id = m.institution_id '
        f'where m.edition_id = %s and r.lat is not null '
        # Not grouped by region: the registry occasionally records two
        # different subdivisions against one set of coordinates, and
        # grouping on it split 22 cities into two points sitting on exactly
        # the same spot with their researchers divided between them.
        f'group by r.city, r.country_code, r.lat, r.lng '
        f'order by researchers desc',
        (limit_institutes, f'{kind}-{year}'))
    return [{'city': city, 'region': region or '',
             'country_code': (country or '').upper(),
             'lat': float(lat), 'lng': float(lng),
             'researchers': int(researchers),
             'citations': int(citations or 0), 'papers': int(papers or 0),
             'h': int(best_h or 0),
             'institutes': [name for name in (institutes or []) if name]}
            for (city, region, country, lat, lng, researchers, citations,
                 papers, best_h, institutes) in rows]


# The names this dashboard's country codes convert to, against the names the
# world outline in assets/ actually uses. 145 of the 175 countries in
# career-2024 agree without help; these are the rest, and the six at the top
# are 8,008 of the 8,058 researchers behind the disagreement.
#
# Taiwan, Hong Kong and Macau have no feature in that outline at all, so they
# cannot be coloured whatever they are called. That is 3,492 researchers in
# career-2024, and it is a property of the map file rather than a decision
# made here.
_MAP_NAMES = {
    'kor': 'Korea',
    'brn': 'Brunei',
    'tur': 'Turkey',
    'cze': 'Czech Rep.',
    'bih': 'Bosnia and Herz.',
    'kgz': 'Kyrgyzstan',
    'civ': "Côte d'Ivoire",
    'fro': 'Faeroe Is.',
    'lao': 'Lao PDR',
    'caf': 'Central African Rep.',
    'cod': 'Dem. Rep. Congo',
    'cuw': 'Curaçao',
    'cym': 'Cayman Is.',
    'lca': 'Saint Lucia',
    'prk': 'Dem. Rep. Korea',
    'pyf': 'Fr. Polynesia',
    'ssd': 'S. Sudan',
    'swz': 'Swaziland',
    'mkd': 'Macedonia',
}


@lru_cache(maxsize=1)
def _converted_names():
    """Every country code in the data, converted in one call.

    country_converter takes about 15 ms per lookup and there are 175 codes,
    so asking it one at a time cost 2.6 seconds on the first view of the map.
    Asked for the whole list at once it takes a fraction of that, and the
    answer is the same for every edition.
    """
    rows = _fetch('select distinct country_code from countries')
    codes = sorted(str(code).upper() for (code,) in rows if code)
    # The defunct states have no name to convert to and no feature on the
    # outline either, so they are left out of the question rather than asked
    # about and refused. They keep the '' every unnamed code gets.
    askable = [code for code in codes if code.lower() not in _DEFUNCT_CODES]
    if not askable:
        return {code.lower(): '' for code in codes}
    converted = coco.convert(names=askable, to='name_short')
    if isinstance(converted, str):
        converted = [converted]
    names = {code.lower(): ('' if str(name).lower() == 'not found' else name)
             for code, name in zip(askable, converted)}
    for code in codes:
        names.setdefault(code.lower(), '')
    return names


def map_name(country_code):
    """What the world outline calls this country, or '' if it has no feature.

    The fact tables carry ISO3. The outline carries names, and its own
    spellings of them: 'Czech Rep.', 'Lao PDR', 'Dem. Rep. Congo'.
    """
    if not country_code:
        return ''
    code = str(country_code).lower()
    if code in _MAP_NAMES:
        return _MAP_NAMES[code]
    return _converted_names().get(code, '')


@lru_cache(maxsize=32)
def country_points(kind, year):
    """Every country the selected edition's researchers work in.

    Unlike city_points this asks the fact table directly rather than going
    through institution_ror, because every row carries a country while only
    the located ones carry coordinates. So the country view is the whole
    edition and the city view is the seven tenths of it that could be placed.
    """
    table = _TABLE_BY_KIND.get(kind)
    if table is None:
        return []
    rows = _fetch(
        f'select country_code, count(*), sum(nc), sum(np), max(h) '
        f'from {table} '
        f'where edition_id = %s and country_code is not null '
        f'group by country_code order by count(*) desc',
        (f'{kind}-{year}',))
    points = []
    for code, researchers, citations, papers, best_h in rows:
        name = map_name(code)
        if not name:
            continue
        points.append({'country_code': code.upper(), 'name': name,
                       'researchers': int(researchers),
                       'citations': int(citations or 0),
                       'papers': int(papers or 0),
                       'h': int(best_h or 0)})
    return points


def city_researchers(lat, lng, kind, year, limit=None):
    """Who works at one point on the map, and how many there are.

    Returns (rows, total), the rows shaped like country_researchers' so the
    same table can show either, and the total the true count rather than the
    length of a page of it.

    Keyed on the coordinates rather than on the name, because a name is not
    unique even inside one country: there are Clevelands in Ohio and in
    Tennessee, and Oxfords in Massachusetts, Mississippi and Ohio. The map
    draws them as separate points and a click has to mean the one that was
    clicked. The rounding matches what city_points puts in the payload, so
    the two always agree about which point this is.
    """
    table = _TABLE_BY_KIND.get(kind)
    if table is None:
        return [], 0
    # The year arrives as a string when it comes from the slider's keyboard
    # step, and as an int everywhere else. Both name the same edition, so
    # they are made the same thing here rather than filling the cache twice.
    year = int(year)
    edition_id = f'{kind}-{year}'
    # Within a hundred metres of the point, rather than equal to it after
    # rounding. The payload carries three decimals and the table carries the
    # registry's full precision, and the two languages do not round halves
    # the same way: Python rounds to even and Postgres rounds away from
    # zero, which is enough to miss a city outright. Nothing on this map is
    # a hundred metres from another place.
    where = ('where m.edition_id = %s '
             'and abs(r.lat - %s) < 0.001 and abs(r.lng - %s) < 0.001')
    params = (edition_id, float(lat), float(lng))
    total = _fetch(
        f'select count(*) from {table} m '
        f'join institution_ror r on r.institution_id = m.institution_id '
        f'{where}', params)[0][0]
    rows = _fetch(
        f'select a.authfull_display, i.inst_name from {table} m '
        f'join institution_ror r on r.institution_id = m.institution_id '
        f'join authors a on a.author_id = m.author_id '
        f'left join institutions i on i.institution_id = m.institution_id '
        f'{where} order by m.c desc nulls last'
        + (' limit %s' if limit else ''),
        params + ((limit,) if limit else ()))
    return ([{'INSTITUTE': inst or '', 'RESEARCHER': name}
             for name, inst in rows], int(total))
