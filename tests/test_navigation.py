"""Every page must be reachable without typing a URL.

Dash registers a page the moment its module is imported and links to none of
them. Two pages shipped that way, reachable only by guessing the path, which
is the same as not shipping them.
"""
import subprocess
import sys


def _nav_links():
    out = subprocess.run(
        [sys.executable, "-c",
         "import app, json;"
         "print(json.dumps([[c.children, c.href] for c in app._nav().children]))"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    import json
    return json.loads(out.stdout.strip().splitlines()[-1])


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
    missing = registered - linked - {'/keke'}
    assert not missing, f"registered but unreachable: {sorted(missing)}"


def test_the_scratch_page_is_not_advertised():
    """pages/test.py sits at a guessable public route and is 186 lines of
    `import *`. It should not be in the navigation, and ideally should not
    ship at all."""
    assert '/keke' not in {href for _label, href in _nav_links()}


def test_home_comes_first():
    labels = [label for label, _href in _nav_links()]
    assert labels[0] == 'Twopercenters'


def test_the_links_are_named_not_pathed():
    """A nav reading '/ranking' tells a reader nothing."""
    for label, href in _nav_links():
        assert label and not label.startswith('/'), (label, href)
