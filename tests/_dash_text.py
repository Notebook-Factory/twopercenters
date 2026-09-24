"""Read a Dash component tree the way a reader sees it."""


def walk(node):
    """Every component in a tree, the root first."""
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from walk(child)
        return
    yield node
    children = getattr(node, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from walk(child)
    elif children is not None and not isinstance(children, str):
        yield from walk(children)


def text_of(node):
    """All the text in a tree, joined with spaces."""
    if node is None:
        return ''
    if isinstance(node, (str, int, float)):
        return str(node)
    if isinstance(node, (list, tuple)):
        return ' '.join(text_of(child) for child in node)
    return text_of(getattr(node, 'children', None))


def links_in(node):
    """The href of every link in a tree."""
    return [getattr(n, 'href', None) for n in walk(node)
            if getattr(n, 'href', None)]
