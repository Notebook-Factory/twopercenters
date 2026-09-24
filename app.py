import dash
import dash_bootstrap_components as dbc

from dash import Dash, html, dcc
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
           ],
           suppress_callback_exceptions=True)
server = app.server

app.title = "Evidence"
# The pages exist only if a reader can get to them. Dash registers a page the
# moment its module is imported, but it puts no link anywhere, so /retraction
# and /ranking were reachable only by typing the URL. This builds the bar from
# dash.page_registry, which means a page added later appears here without an
# edit.

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
        icon = _NAV_ICONS.get(page['path'])
        label = [html.I(**{'data-lucide': icon})] if icon else []
        label.append(html.Span(page['name']))
        links.append(dcc.Link(label, href=page['path'],
                              className='ev-nav-link'))
    return html.Nav(links, className='ev-nav')


app.layout = html.Div([
	_nav(),
	dash.page_container
])

# Importing the pages above runs queries at import time (pages/home.py,
# pages/retraction.py and pages/rfm.py build their first figures), which
# leaves citations_lib.utils._conn open. cfg.py sets gunicorn's
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
