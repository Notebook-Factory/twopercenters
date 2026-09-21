"""The precomputed top ten has to be the true top ten.

A table that a pipeline step fills and the dashboard reads is only worth
having if it says what the fact table says. Everything here asks the fact
table directly and compares, for every metric and both column sets, rather
than trusting the fill.
"""
import pytest

from citations_lib.utils import COMPOSITE_METRICS, _fetch

EDITIONS = [('career', 2024), ('career', 2017), ('singleyr', 2024)]
METRICS = ('c',) + COMPOSITE_METRICS
TABLE = {'career': 'career_metrics', 'singleyr': 'singleyr_metrics'}


def _live(kind, year, metric, ns):
    suffix = '_ns' if ns else ''
    return _fetch(
        f'select author_id, {metric}{suffix} from {TABLE[kind]} '
        f'where edition_id = %s and {metric}{suffix} is not null '
        f'order by {metric}{suffix} desc, author_id limit 10',
        (f'{kind}-{year}',))


def _stored(kind, year, metric, ns):
    return _fetch(
        'select author_id, value from top_researchers '
        'where edition_id = %s and metric = %s and ns = %s '
        'order by position', (f'{kind}-{year}', metric, ns))


@pytest.mark.parametrize('kind,year', EDITIONS)
@pytest.mark.parametrize('metric', METRICS)
@pytest.mark.parametrize('ns', [False, True])
def test_stored_top_ten_equals_the_live_top_ten(kind, year, metric, ns):
    live = _live(kind, year, metric, ns)
    stored = _stored(kind, year, metric, ns)
    assert [author for author, _ in stored] == [author for author, _ in live]
    assert ([pytest.approx(value) for _, value in stored]
            == [value for _, value in live])


@pytest.mark.parametrize('kind,year', EDITIONS)
def test_positions_run_one_to_ten(kind, year):
    rows = _fetch(
        'select metric, ns, array_agg(position order by position) '
        'from top_researchers where edition_id = %s group by metric, ns',
        (f'{kind}-{year}',))
    assert rows
    for metric, ns, positions in rows:
        assert positions == list(range(1, 11)), (metric, ns)


def test_the_two_column_sets_are_not_the_same_column():
    """A fill that read the published column for both variants would pass
    every test above. This is the one that catches it."""
    plain = _stored('career', 2024, 'nc', False)
    excluded = _stored('career', 2024, 'nc', True)
    assert [value for _, value in plain] != [value for _, value in excluded]
