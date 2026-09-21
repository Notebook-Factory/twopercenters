"""The precomputed top ten has to be the true top ten.

A table that a pipeline step fills and the dashboard reads is only worth
having if it says what the fact table says. Everything here asks the fact
table directly and compares, for every metric and both column sets, rather
than trusting the fill.
"""
import pytest

from citations_lib.utils import (COMPOSITE_METRICS, _fetch, author_metrics,
                                 top_researchers)

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


# ---------------------------------------------------------------------------
# What the dashboard actually calls
# ---------------------------------------------------------------------------

def test_top_researchers_resolves_names_and_keeps_order():
    rows = top_researchers('career', 2024, 'ncsf')
    assert len(rows) == 10
    assert [row['position'] for row in rows] == list(range(1, 11))
    assert all(row['name'] for row in rows)
    values = [row['value'] for row in rows]
    assert values == sorted(values, reverse=True)


def test_the_fallback_returns_what_the_table_returns():
    """The tab has to work on a database where 012 has been applied but the
    pipeline has not run since, so the live path has to agree with the stored
    one rather than merely exist."""
    stored = top_researchers('career', 2024, 'ncsf')
    live = top_researchers('career', 2024, 'ncsf', _force_live=True)
    assert [row['author_id'] for row in stored] == [row['author_id']
                                                    for row in live]
    assert [row['value'] for row in stored] == [row['value'] for row in live]


def test_the_self_citation_variant_asks_a_different_question():
    plain = top_researchers('career', 2024, 'nc')
    excluded = top_researchers('career', 2024, 'nc', ns=True)
    assert [r['value'] for r in plain] != [r['value'] for r in excluded]


def test_author_metrics_returns_the_row_the_card_needs():
    top = top_researchers('career', 2024, 'c')[0]
    data = author_metrics(top['author_id'], 'career', 2024)
    assert data['name'] == top['name']
    for metric in ('nc', 'h', 'hm', 'ncs', 'ncsf', 'ncsfl', 'c'):
        assert data[metric] is not None
        assert data[metric + '_ns'] is not None


def test_author_metrics_is_silent_about_an_author_not_in_the_edition():
    assert author_metrics('no-such-author', 'career', 2024) is None
