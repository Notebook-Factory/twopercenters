"""gunicorn configuration. The Procfile runs `gunicorn app:server -c cfg.py`.

The one thing in here that is not a default is post_fork, and it exists
because of a real deployment hazard rather than a preference.

preload_app is on, which means gunicorn imports app.py in the MASTER process
and then forks the workers. pages/home.py does two database reads at import
time -- update_yr_options2(True) for the year buttons and get_world_df(...)
for the map's first frame -- so by the time the fork happens, the master
holds an open connection in citations_lib.utils._conn. A forked child
inherits the same libpq socket. Two workers sharing one connection interleave
their requests on it, which produces protocol errors and, in the bad case,
one request reading another request's result set. It cannot be reproduced
with `python app.py`, which is a single process.

There are two guards against it and both are deliberate:

  1. app.py calls citations_lib.utils.close_db() at the end of its own
     import, so the master has nothing open at fork time. This is the one
     that actually fixes it, and tests/test_no_shared_connection.py asserts
     it.
  2. post_fork below sets utils._conn to None in each child. This is the
     belt-and-braces half: it does not close the connection (a child closing
     an inherited connection would send libpq's terminate message and kill it
     for the master and every sibling), it just makes the child forget it and
     open its own on first use. It covers the case where something opens a
     connection after app.py's import finishes but before the fork.

Deliberately NOT set here: `bind`. gunicorn already defaults to
0.0.0.0:$PORT when PORT is in the environment, which is how dokku hands an
app its port. An earlier version of this file pinned 127.0.0.1:8050, which is
a laptop address and would have made the app unreachable on the host. Nothing
referenced this file at the time, so nothing broke; it does now.
"""

preload_app = True
workers = 2
threads = 1
timeout = 3000


def post_fork(server, worker):
    from citations_lib import utils

    utils._conn = None
    server.log.info("worker %s: reset the inherited database connection",
                    worker.pid)
