import dash
import dash_bootstrap_components as dbc
import pandas as pd
import os

from dash import Dash, html, dcc, callback
from dash.dependencies import Input, Output, State
import warnings

from elasticsearch.exceptions import ElasticsearchWarning
warnings.simplefilter('ignore', ElasticsearchWarning)


app = Dash(__name__, use_pages=True, external_stylesheets=[dbc.themes.SLATE],
           # Lucide: the icon set the dashboard uses. It replaces any
           # <i data-lucide="name"> with an inline SVG that inherits
           # currentColor, so icons follow the theme like text does.
           external_scripts=[
               "https://unpkg.com/lucide@latest/dist/umd/lucide.js",
               # ECharts draws the rank strip on the author card, which is
               # the one picture on the site that has to put two numbers
               # 15,000 apart on the same axis and stay readable. It is
               # loaded from the CDN and driven by a clientside callback, so
               # nothing new is installed on the Python side and no other
               # chart on the site changes.
               "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js",
               # And echarts-gl, for one chart. The city map draws 3,341
               # points that have to stay smooth while the map is dragged,
               # and in plain canvas they are half the cost of a frame. This
               # is the package the scatterGL example uses.
               #
               # It is an addition, not a replacement: the map feature-tests
               # for the series and falls back to the canvas scatter when
               # the script has not loaded or the machine has no WebGL.
               "https://cdn.jsdelivr.net/npm/echarts-gl@2.0.9/dist/echarts-gl.min.js",
           ],
           suppress_callback_exceptions=True)
server = app.server
app.title = "Evidence"
# The pages exist only if a reader can get to them. Dash registers a page the
# moment its module is imported, but it puts no link anywhere, so /retraction
# and /ranking were reachable only by typing the URL. This builds the bar from
# dash.page_registry, which means a page added later appears here without an
# edit; the scratch page at /keke is excluded by name.
_HIDDEN_ROUTES = {'/keke'}

# A Lucide glyph per route. Keyed by path rather than by name so renaming a
# page does not silently drop its icon.
_NAV_ICONS = {
    '/': 'home',
    '/ranking': 'list-ordered',      # the list, and where you sit in it
    '/retraction': 'file-x',         # a paper withdrawn
    '/predictions': 'waypoints',     # a graph, which is what the model reads
}

# The order the bar reads in, rather than alphabetical: home, then the two
# explanatory pages.
_NAV_ORDER = ['/', '/ranking', '/retraction', '/predictions']


def _nav():
    def rank(page):
        try:
            return _NAV_ORDER.index(page['path'])
        except ValueError:
            return len(_NAV_ORDER)

    links = []
    for page in sorted(dash.page_registry.values(),
                       key=lambda p: (rank(p), p['name'])):
        if page['path'] in _HIDDEN_ROUTES:
            continue
        icon = _NAV_ICONS.get(page['path'])
        label = [html.I(**{'data-lucide': icon})] if icon else []
        label.append(html.Span(page['name']))
        links.append(dcc.Link(label, href=page['path'],
                              className='ev-nav-link'))
    return html.Nav(links, className='ev-nav')


app.layout = html.Div([
        html.Div([dcc.Store(id="df-store", storage_type='local'),
            dcc.Interval(
            id="load_interval", 
            n_intervals=0, 
            max_intervals=0,
            interval=1)]),
	_nav(),
	dash.page_container
])

# Importing the pages above ran two queries at import time (pages/home.py's
# year options and the world map's first frame), which left
# citations_lib.utils._conn open. The Procfile runs gunicorn with
# preload_app, so this module is imported in the MASTER process and the
# workers are forked from it -- and a forked child inherits the same libpq
# socket, so two workers would interleave their requests on one connection.
# Closing here means nothing is inherited; each worker opens its own on its
# first query. cfg.py's post_fork hook is the second guard, and
# tests/test_no_shared_connection.py asserts this line has not been lost.
from citations_lib.utils import close_db as _close_db

_close_db()



if __name__ == '__main__':
	app.run_server(debug=False)

# app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SLATE],
#                 meta_tags=[
#                     {"name": "viewport", "content": "width=device-width,height=device-height, initial-scale=1"}
#                 ], suppress_callback_exceptions = True)
# server = app.server

# TODO: Arrange for deployment
# cache = Cache(server, config={
# 'CACHE_TYPE': 'redis',
    # Note that filesystem cache doesn't work on systems with ephemeral
    # filesystems like Heroku.
# 'CACHE_TYPE': 'filesystem',
# 'CACHE_DIR': 'cache-directory',

    # should be equal to maximum number of users on the app at a single time
    # higher numbers will store more data in the filesystem / redis cache
#    'CACHE_THRESHOLD': 2
# })

# cache = Cache()
# cache_servers = os.environ.get('MEMCACHIER_SERVERS')
# if cache_servers == None:
#     # Fall back to simple in memory cache (development)
#     cache.init_app(server, config={'CACHE_TYPE': 'simple'})
# else:
#     cache_user = os.environ.get('MEMCACHIER_USERNAME') or ''
#     cache_pass = os.environ.get('MEMCACHIER_PASSWORD') or ''
#     cache.init_app(server,
#         config={'CACHE_TYPE': 'saslmemcached',
#                 'CACHE_MEMCACHED_SERVERS': cache_servers.split(','),
#                 'CACHE_MEMCACHED_USERNAME': cache_user,
#                 'CACHE_MEMCACHED_PASSWORD': cache_pass,
#                 'CACHE_OPTIONS': { 'behaviors': {
#                     # Faster IO
#                     'tcp_nodelay': True,
#                     # Keep connection alive
#                     'tcp_keepalive': True,
#                     # Timeout for set/get requests
#                     'connect_timeout': 2000, # ms
#                     'send_timeout': 750 * 1000, # us
#                     'receive_timeout': 750 * 1000, # us
#                     '_poll_timeout': 2000, # ms
#                     # Better failover
#                     'ketama': True,
#                     'remove_failed': 1,
#                     'retry_timeout': 2,
#                     'dead_timeout': 30}}})
'''
def get_dataframe(session_id):
    @cache.memoize()
    def query_and_serialize_data(session_id):
        
        phan_df = pd.read_pickle('3T_NIST_T1maps_database.pkl')

        return phan_df.to_json()

    return pd.read_json(query_and_serialize_data(session_id))

def get_dataframe_brain(session_id):
    @cache.memoize()
    def query_and_serialize_data(session_id):
        
        brain_df = pd.read_pickle('3T_human_T1maps_database.pkl')

        return brain_df.to_json()

    return pd.read_json(query_and_serialize_data(session_id))
'''