"""Every page must be reachable without typing a URL.

Dash registers a page the moment its module is imported and links to none of
them. Two pages shipped that way, reachable only by guessing the path, which
is the same as not shipping them.
"""
import functools
import subprocess
import sys


@functools.lru_cache(maxsize=1)
def _nav_links():
    out = subprocess.run(
        [sys.executable, "-c",
         "import app, json;"
         # The last child of each link is the Span with its name; the
         # first, when there is one, is the icon.
         "print(json.dumps([[c.children[-1].children, c.href]"
         " for c in app._nav().children]))"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    import json
    return tuple(tuple(link) for link in
                 json.loads(out.stdout.strip().splitlines()[-1]))


def test_every_public_page_has_a_link():
    out = subprocess.run(
        [sys.executable, "-c",
         "import app, dash, json;"
         "print(json.dumps(sorted(p['path'] for p in dash.page_registry.values())))"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    import json
    registered = set(json.loads(out.stdout.strip().splitlines()[-1]))
    linked = {href for _label, href in _nav_links()}
    missing = registered - linked
    assert not missing, f"registered but unreachable: {sorted(missing)}"


def test_home_comes_first():
    labels = [label for label, _href in _nav_links()]
    assert labels[0] == 'Twopercenters'


def test_the_links_are_named_not_pathed():
    """A nav reading '/ranking' tells a reader nothing."""
    for label, href in _nav_links():
        assert label and not label.startswith('/'), (label, href)


def test_the_spotlight_overlay_has_a_close_control():
    """"esc to close" is an instruction, not a control. It leaves anyone on a
    mouse, or a touch screen with no esc key, with no way out of the
    overlay."""
    source = open("pages/home.py").read()
    assert 'id="spotlight-close"' in source
    assert 'ev-overlay-close' in source
    assert 'Input("spotlight-close", "n_clicks")' in source


def test_the_close_control_is_labelled_for_a_screen_reader():
    source = open("pages/home.py").read()
    assert '"aria-label": "Close search"' in source
