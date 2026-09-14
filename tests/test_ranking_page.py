"""The page that explains how a rank can exceed the size of the list."""
import subprocess
import sys

import pytest

from citations_lib.utils import RANK_CUTOFF, rank_coverage


def test_every_rank_up_to_the_cutoff_is_published():
    """The measurement the whole page rests on, checked on the data rather
    than asserted in prose. Verified across all eight career editions; 2018
    is two short of 100,000, which is why this allows a hair under."""
    for year in range(2017, 2025):
        data = rank_coverage('career', year)
        full = [b for b in data['bands'] if b['high'] <= RANK_CUTOFF]
        assert full, year
        for band in full:
            assert band['share'] > 0.9999, (year, band)


def test_coverage_decays_past_the_cutoff():
    """And keeps decaying, which is what makes the subfield rule visible."""
    data = rank_coverage('career', 2019)
    beyond = [b for b in data['bands'] if b['low'] > RANK_CUTOFF]
    assert len(beyond) >= 4
    shares = [b['share'] for b in beyond]
    assert shares == sorted(shares, reverse=True)
    assert shares[0] < 0.6
    assert shares[-1] < 0.01


def test_the_largest_rank_exceeds_the_published_size():
    """Which is the fact a reader trips over and comes here to understand."""
    data = rank_coverage('career', 2019)
    assert data['highest_rank'] > data['published']


def test_an_unknown_kind_is_not_an_error():
    assert rank_coverage('nonsense', 2019) == []


def test_the_first_band_starts_at_rank_one():
    """Integer division rounded it to '0-25k', claiming a rank nobody has."""
    import app  # noqa: F401  (register_page needs the app instantiated)
    import pages.ranking as ranking
    data = rank_coverage('career', 2019)
    assert ranking._label(data['bands'][0]).startswith('1-')


def test_a_rank_inside_the_cutoff_reads_differently_from_one_beyond_it():
    import app  # noqa: F401
    import pages.ranking as ranking
    _fig, inside = ranking._update(2019, 5_000)
    _fig2, beyond = ranking._update(2019, 214_011)
    assert str(inside) != str(beyond)
    assert 'entirely' in str(inside)
    assert 'subfield standing' in str(beyond)


def test_the_page_is_registered():
    out = subprocess.run(
        [sys.executable, "-c",
         "import app, dash;"
         "print(sorted(p['path'] for p in dash.page_registry.values()))"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "/ranking" in out.stdout
