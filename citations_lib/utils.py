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


def es_scroll(index, query_body, page_size=100, debug=False, scroll='2m'):
    page = es.search(index=index, scroll=scroll, size=page_size, body=query_body)
    sid = page['_scroll_id']
    scroll_size = page['hits']['total']['value']
    total_pages = math.ceil(scroll_size/page_size)
    page_counter = 0
    if debug: 
        print('Total items : {}'.format(scroll_size))
        print('Total pages : {}'.format( math.ceil(scroll_size/page_size) ) )
    # Start scrolling
    while (scroll_size > 0):
        # Get the number of results that we returned in the last scroll
        scroll_size = len(page['hits']['hits'])
        if scroll_size>0:
            if debug: 
                print('> Scrolling page {} : {} items'.format(page_counter, scroll_size))
            yield total_pages, page_counter, scroll_size, page
        # get next page
        page = es.scroll(scroll_id = sid, scroll = '2m')
        page_counter += 1
        # Update the scroll ID
        sid = page['_scroll_id']

def get_index_cat(index_name):
    params = {"bytes":"b","format":"json"}
    return es.cat.indices(index=index_name,params=params)

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


def _fetch(sql, params=()):
    global _conn
    for attempt in (1, 2):
        try:
            with _db().cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        except psycopg.Error:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
            if attempt == 2:
                raise


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

    Three codes in the data are defunct states that country_converter cannot
    resolve: csk (Czechoslovakia), scg (Serbia and Montenegro) and sux (the
    Soviet Union). The pickles left them out of the country dropdown and so
    does this, since the label would read 'not found' and selecting one would
    fail the same conversion in get_es_aggregate.
    """
    if code not in _COUNTRY_NAMES:
        name = coco.convert(names=code, to='name_short')
        _COUNTRY_NAMES[code] = None if name == 'not found' else name
    return _COUNTRY_NAMES[code]


def _dropdown_lists(kind):
    """{edition_id: {'cntry': [...], 'cntry_full': [...], 'inst_name': [...],
    'sm-field': [...]}}: the option lists the group dropdowns offer."""
    table = _TABLE_BY_KIND[kind]
    out = {}

    def collect(key, rows):
        for edition_id, value in rows:
            out.setdefault(edition_id, {}).setdefault(key, []).append(value)

    collect('cntry', _fetch(
        f'select edition_id, country_code from {table} '
        f'where country_code is not null group by 1, 2 order by 1, 2'))
    collect('inst_name', _fetch(
        f'select m.edition_id, i.inst_name from {table} m '
        f'join institutions i on i.institution_id = m.institution_id '
        f'group by 1, 2 order by 1, 2'))
    collect('sm-field', _fetch(
        f'select m.edition_id, f.name from {table} m '
        f'join fields f on f.field_id = m.field_id '
        f'group by 1, 2 order by 1, 2'))
    for lists in out.values():
        pairs = [(code, _country_full_name(code))
                 for code in lists.get('cntry', [])]
        pairs = [(code, name) for code, name in pairs if name is not None]
        # The two lists are zipped together to label the country dropdown, so
        # they have to stay aligned.
        lists['cntry'] = [code for code, _ in pairs]
        lists['cntry_full'] = [name for _, name in pairs]
    return out


def _dropdown_stats(kind):
    """{edition_id: {'nc min': ..., 'nc max': ..., 'nc mean': ...,
    'nc std': ...}}, one entry per metric, as the pickles held them."""
    table = _TABLE_BY_KIND[kind]
    selects = []
    for _, column in _DROPDOWN_METRICS:
        selects += [f'min({column})', f'max({column})', f'avg({column})',
                    f'stddev_samp({column})']
    rows = _fetch(f'select edition_id, {", ".join(selects)} '
                  f'from {table} group by edition_id')
    out = {}
    for row in rows:
        stats = {}
        for i, (name, _) in enumerate(_DROPDOWN_METRICS):
            minimum, maximum, mean, std = row[1 + i * 4:5 + i * 4]
            stats[f'{name} min'] = minimum
            stats[f'{name} max'] = maximum
            # The pickles stored these rounded to two decimals.
            stats[f'{name} mean'] = None if mean is None else round(float(mean), 2)
            stats[f'{name} std'] = None if std is None else round(float(std), 2)
        out[row[0]] = stats
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
        live = institution_aggregate_by_name(_db(), group_value, kind)
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


def es_result_pick(result,field, nohit = ['']):
    """Pull one field out of a get_es_results() frame.

    field='data' is the interesting case: it no longer decompresses a blob
    out of the search hit, it reads that author's rows from Postgres and
    assembles the same nested dict.
    """
    if result is None or len(result) == 0:
        return nohit
    if field == 'data':
        # The old index held one document per author name covering every year
        # that name appeared, and the layouts still look a name up and expect
        # all of its editions back. Identity resolution can now split one
        # display name across several author_ids, so gather every hit
        # carrying the top hit's exact name, richest first.
        wanted = result['_source.authfull'].iloc[0]
        same_name = result[result['_source.authfull'] == wanted]
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
    """
    if not search_term:
        return None
    kinds = _requested_kinds(idx_name)
    if exact:
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
    result = es.search(index=AUTHOR_ALIAS, size=100,
                       body={"query": query, "_source": _SOURCE_FIELDS})
    hits = result.get('hits', {}).get('hits', [])
    if not hits:
        return None
    records = []
    for hit in hits:
        source = hit['_source']
        # years_present holds hyphenated edition ids, so the kind is what
        # comes before the hyphen.
        present = {edition.partition('-')[0]
                   for edition in source.get('years_present', [])}
        for kind in kinds:
            if kind not in present:
                continue
            record = {f'_source.{key}': value for key, value in source.items()}
            # callback_templates reads result['_index'] and looks for the
            # literal strings 'career' and 'singleyr' in it to decide which
            # radio buttons to enable. That used to be the index name.
            record['_index'] = kind
            record['_id'] = hit['_id']
            record['_score'] = hit['_score']
            record['_editions'] = len(source.get('years_present', []))
            records.append(record)
    if not records:
        return None
    # Hits arrive in relevance order. Within one name, prefer the author_id
    # that covers the most editions, so es_result_pick(result, 'data') reads
    # the fuller record when identity resolution split a display name.
    frame = pd.DataFrame.from_records(records)
    frame = frame.sort_values('_editions', ascending=False, kind='stable')
    return frame.reset_index(drop=True)

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
    yrs = [2017, 2018, 2019, 2020, 2021]
    if yr == 0: year = 2017
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
    
def load_standardized_data(root_data = 'data/'):

    # =============== Reading in the data

    maxlog_metrics = ['nc', 'h', 'hm',  'ncs', 'ncsf','ncsfl', 'nc (ns)', 'h (ns)', 'hm (ns)',  'ncs (ns)', 'ncsf (ns)','ncsfl (ns)']

    # === 2017 data
    data_path = root_data + 'version-1/'
    df_career_v1_2017 = pd.read_pickle(data_path + 'Table-S1-career-2017.pkl')
    df_career_v1_2017_log = pd.read_pickle(data_path + 'Table-S1-career-2017_LogTransform.pkl')
    df_singleyr_v1_2017 = pd.read_pickle(data_path + 'Table-S2-singleyr-2017.pkl')
    df_singleyr_v1_2017_log = pd.read_pickle(data_path + 'Table-S2-singleyr-2017_LogTransform.pkl')
    # standardize col names
    df_career_v1_2017, df_career_v1_2017_text = standardize_col_names(df = df_career_v1_2017, year = 2017, v1_present = True, singleyr = False)
    df_career_v1_2017_log, _ = standardize_col_names(df = df_career_v1_2017_log, year = 2017, v1_present = True, singleyr = False)
    df_singleyr_v1_2017, df_singleyr_v1_2017_text = standardize_col_names(df = df_singleyr_v1_2017, year = 2017, v1_present = True, singleyr = True)
    df_singleyr_v1_2017_log, _ = standardize_col_names(df = df_singleyr_v1_2017_log, year = 2017, v1_present = True, singleyr = True)

    # === 2018 data (only career data available!)
    df_career_v1_2018 = pd.read_pickle(data_path + 'Table-S4-career-2018.pkl')
    df_career_v1_2018_log = pd.read_pickle(data_path + 'Table-S4-career-2018_LogTransform.pkl')
    # standardize col names
    df_career_v1_2018, df_career_v1_2018_text = standardize_col_names(df = df_career_v1_2018, year = 2018, v1_present = True, singleyr = False)
    df_career_v1_2018_log, _ = standardize_col_names(df = df_career_v1_2018_log, year = 2018, v1_present = True, singleyr = False)

    # === 2019 data
    data_path = root_data + 'version-2/'
    df_career_v2_2019 = pd.read_pickle(data_path + 'Table-S6-career-2019.pkl')
    df_career_v2_2019_log = pd.read_pickle(data_path + 'Table-S6-career-2019_LogTransform.pkl')
    df_singleyr_v2_2019 = pd.read_pickle(data_path + 'Table-S7-singleyr-2019.pkl')
    df_singleyr_v2_2019_log = pd.read_pickle(data_path + 'Table-S7-singleyr-2019_LogTransform.pkl')
    # standardize col names
    df_career_v2_2019, df_career_v2_2019_text = standardize_col_names(df = df_career_v2_2019, year = 2019, v1_present = True, singleyr = False)
    df_career_v2_2019_log, _ = standardize_col_names(df = df_career_v2_2019_log, year = 2019, v1_present = True, singleyr = False)
    df_singleyr_v2_2019, df_singleyr_v2_2019_text = standardize_col_names(df = df_singleyr_v2_2019, year = 2019, v1_present = True, singleyr = True)
    df_singleyr_v2_2019_log, _ = standardize_col_names(df = df_singleyr_v2_2019_log, year = 2019, v1_present = True, singleyr = True)

    # === 2020 data
    data_path = root_data + 'version-3/'
    df_career_v3_2020 = pd.read_pickle(data_path + 'Table_1_Authors_career_2020_wopp_extracted_202108.pkl')
    df_career_v3_2020_log = pd.read_pickle(data_path + 'Table_1_Authors_career_2020_wopp_extracted_202108_LogTransform.pkl')
    df_singleyr_v3_2020 = pd.read_pickle(data_path + 'Table_1_Authors_singleyr_2020_wopp_extracted_202108.pkl')
    df_singleyr_v3_2020_log = pd.read_pickle(data_path + 'Table_1_Authors_singleyr_2020_wopp_extracted_202108_LogTransform.pkl')
    # standardize col names
    df_career_v3_2020, df_career_v3_2020_text = standardize_col_names(df = df_career_v3_2020, year = 2020, v1_present = True, singleyr = False)
    df_career_v3_2020_log, _ = standardize_col_names(df = df_career_v3_2020_log, year = 2020, v1_present = True, singleyr = False)
    df_singleyr_v3_2020, df_singleyr_v3_2020_text = standardize_col_names(df = df_singleyr_v3_2020, year = 2020, v1_present = True, singleyr = True)
    df_singleyr_v3_2020_log, _ = standardize_col_names(df = df_singleyr_v3_2020_log, year = 2020, v1_present = True, singleyr = True)

    # === 2021 data
    data_path = root_data + 'version-5/'
    df_career_v5_2021 = pd.read_pickle(data_path + 'Table_1_Authors_career_2021_pubs_since_1788_wopp_extracted_202209b.pkl')
    df_career_v5_2021_log = pd.read_pickle(data_path + 'Table_1_Authors_career_2021_pubs_since_1788_wopp_extracted_202209b_LogTransform.pkl')
    df_singleyr_v5_2021 = pd.read_pickle(data_path + 'Table_1_Authors_singleyr_2021_pubs_since_1788_wopp_extracted_202209b.pkl')
    df_singleyr_v5_2021_log = pd.read_pickle(data_path + 'Table_1_Authors_singleyr_2021_pubs_since_1788_wopp_extracted_202209b_LogTransform.pkl')
    # standardize col names
    df_career_v5_2021, df_career_v5_2021_text = standardize_col_names(df = df_career_v5_2021, year = 2021, v1_present = True, singleyr = False)
    df_career_v5_2021_log, _ = standardize_col_names(df = df_career_v5_2021_log, year = 2021, v1_present = True, singleyr = False)
    df_singleyr_v5_2021, df_singleyr_v5_2021_text = standardize_col_names(df = df_singleyr_v5_2021, year = 2021, v1_present = True, singleyr = True)
    df_singleyr_v5_2021_log, _ = standardize_col_names(df = df_singleyr_v5_2021_log, year = 2021, v1_present = True, singleyr = True)

    # =============== Save list of df names and attributes
    dfs_career = [df_career_v1_2017, df_career_v1_2018, df_career_v2_2019, df_career_v3_2020, df_career_v5_2021] ### DELETE: dfs = [df1,df2,df3,df5,df5_career] 
    dfs_singleyr = [df_singleyr_v1_2017, df_singleyr_v2_2019, df_singleyr_v3_2020, df_singleyr_v5_2021]

    dfs_career_log = [df_career_v1_2017_log, df_career_v1_2018_log, df_career_v2_2019_log, df_career_v3_2020_log, df_career_v5_2021_log] ### DELETE: dfs_log = [df1_log,df2_log,df3_log,df5_log,df5_career_log]
    dfs_singleyr_log = [df_singleyr_v1_2017_log, df_singleyr_v2_2019_log, df_singleyr_v3_2020_log, df_singleyr_v5_2021_log]

    dfs_career_text = [df_career_v1_2017_text, df_career_v1_2018_text, df_career_v2_2019_text, df_career_v3_2020_text, df_career_v5_2021_text] ### DELETE: text = [df1_text,df2_text,df3_text,df5_text,df5_career_text]
    dfs_singleyr_text = [df_singleyr_v1_2017_text, df_singleyr_v2_2019_text, df_singleyr_v3_2020_text, df_singleyr_v5_2021_text]
    ### DELETE: names = ['df1','df2','df3','df5','df5_career']

    dfs_career_yrs = [2017, 2018, 2019, 2020, 2021]
    dfs_singleyr_yrs = [2017, 2019, 2020, 2021]

    return(dfs_career, dfs_singleyr, dfs_career_log, dfs_singleyr_log, dfs_career_text, dfs_singleyr_text, dfs_career_yrs, dfs_singleyr_yrs)

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
    cc = coco.CountryConverter()
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
            if code != 'csk' and code != 'nan':
                if code == 'sux':
                    cur_name = "Russia"
                elif code == 'ant':
                    cur_name = "Netherlands"
                elif code == 'scg':
                    cur_name = 'Czech Republic'
                else:
                    cur_name = cc.convert(code, to = 'name_short')
                vector = summary.get((code, metric))
                if vector is not None and vector[st_idx] is not None:
                    df.loc[kk] = ([code.upper()]) + [cur_name] + [vector[st_idx]]  + [''] + [str(metric)] + [str(metrics_name[idxx])]
                else:
                    df.loc[kk] = ([code.upper()]) + [cur_name] + [0] + [''] + [str(metric)] + ['lel']
                kk = kk +1
    return df