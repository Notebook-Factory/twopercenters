"""No database connection survives the import of app.py.

The Procfile runs `gunicorn app:server -c cfg.py`, and cfg.py sets
preload_app. gunicorn therefore imports app.py once in the master process and
forks the workers from it. pages/home.py performs two queries at import time,
which opens citations_lib.utils._conn in the master; a forked child inherits
that same libpq socket, so both workers would be issuing queries down one
connection. The symptoms are protocol errors and, in the bad case, one
request reading another request's result set. `python app.py` is a single
process and cannot reproduce any of it, which is why this is a test rather
than something a click-through would catch.

The invariant these tests hold is not "nothing queries the database at import
time" -- that is a reasonable thing for a page to do and it is how the year
buttons and the first map frame get their data. It is the narrower and more
useful one: by the time importing app.py is finished, this process holds no
open connection, so there is nothing for a fork to share. If someone adds
another import-time query, that stays true. If someone deletes app.py's
close_db() call, or moves it above the page imports, this fails.
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(snippet):
    """Import the app in a clean interpreter and report back.

    A subprocess rather than an in-process import because importing app.py
    registers Dash pages and callbacks globally, and because the whole point
    is to observe a freshly imported module rather than one another test has
    already touched.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO
    done = subprocess.run([sys.executable, "-c", snippet], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-4000:]
    return done.stdout.strip().splitlines()[-1]


def test_importing_app_leaves_no_open_connection():
    last = _run(
        "import app\n"
        "from citations_lib import utils\n"
        "print('CONN', utils._conn is None or utils._conn.closed)\n"
    )
    assert last == "CONN True", (
        "importing app.py left citations_lib.utils._conn open. Under "
        "gunicorn's preload_app every forked worker would inherit that one "
        "connection. Close it at the end of app.py (utils.close_db()), "
        "after the page imports, not before."
    )


def test_the_pages_really_do_query_at_import_time():
    """Guards the test above from quietly becoming vacuous.

    If the pages ever stop reading the database at import, the first test
    passes for a reason that has nothing to do with the fix and would keep
    passing after the fix was deleted. This counts the connections opened
    while app.py is being imported, so the first test is known to be testing
    something. pages/home.py cannot be imported on its own (register_page
    refuses to run before the app exists), so the count is taken around the
    import of app.py itself.
    """
    last = _run(
        "from citations_lib import utils\n"
        "opened = []\n"
        "_real = utils.connect\n"
        "utils.connect = lambda: (opened.append(1), _real())[1]\n"
        "import app\n"
        "print('OPENED', len(opened))\n"
    )
    assert last != "OPENED 0", (
        "nothing opened a database connection while app.py was imported. "
        "That is not a failure in itself, but it makes "
        "test_importing_app_leaves_no_open_connection vacuous -- delete or "
        "rewrite both if this is now the intended shape."
    )


def test_procfile_uses_the_gunicorn_config():
    """The post_fork hook only runs if gunicorn is told to read cfg.py."""
    with open(os.path.join(REPO, "Procfile")) as handle:
        procfile = handle.read()
    assert "-c cfg.py" in procfile or "--config cfg.py" in procfile, procfile


def test_post_fork_detaches_without_closing():
    """post_fork must forget the inherited connection, not close it.

    A child that closes an inherited connection sends libpq's terminate
    message, which tears the connection down for the master and every sibling
    too. So the hook sets the global to None and lets _db() open a fresh one.
    """
    import types

    import cfg
    from citations_lib import utils

    assert cfg.preload_app is True

    class _Fake:
        closed = False

        def close(self):  # pragma: no cover - must not be reached
            raise AssertionError("post_fork closed the inherited connection")

    sentinel = _Fake()
    utils._conn = sentinel
    try:
        log = types.SimpleNamespace(info=lambda *a, **k: None)
        cfg.post_fork(types.SimpleNamespace(log=log),
                      types.SimpleNamespace(pid=1))
        assert utils._conn is None
        assert sentinel.closed is False
    finally:
        utils._conn = None
