"""dash.callback and dash.clientside_callback, registered once per set of
outputs.

The compare tabs and the Explore section are built when a reader opens them,
and their builders declare callbacks as they run. Dash reads its callback
list once, before the first request, so a declaration after that is never
used; with the plain dash functions each one was still appended to the list
and kept for the life of the worker. These versions register a callback the
first time its outputs are declared and ignore every later declaration of
the same outputs.

That is only safe because every panel is built once at import
(pages/home.py), while Dash is still listening.
"""
import dash

_registered = set()


def _key(args, kwargs):
    return repr(args) + repr(sorted(kwargs.items()))


def callback(*args, **kwargs):
    key = _key(args, kwargs)
    if key in _registered:
        return lambda function: function
    _registered.add(key)
    return dash.callback(*args, **kwargs)


def clientside_callback(clientside_function, *args, **kwargs):
    key = _key(args, kwargs)
    if key in _registered:
        return
    _registered.add(key)
    dash.clientside_callback(clientside_function, *args, **kwargs)
