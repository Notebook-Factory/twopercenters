"""The retraction page must never let an estimate look like a measurement."""
import subprocess
import sys

import pytest


def test_the_page_is_registered_at_a_real_route():
    out = subprocess.run(
        [sys.executable, "-c",
         "import app, dash;"
         "print(sorted(p['path'] for p in dash.page_registry.values()))"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "/retraction" in out.stdout


def test_estimates_and_measurements_are_drawn_differently():
    """Colour alone is not enough: a hatch survives greyscale and a
    screenshot. Both the fill and the pattern must differ."""
    source = open("pages/retraction.py").read()
    assert "pattern=dict(shape='/'" in source
    assert "MEASURED = '#00B4D8'" in source
    assert "ESTIMATED = '#A8B2C4'" in source


def test_every_estimate_is_labelled_as_one():
    source = open("pages/retraction.py").read()
    assert "Estimated (never recorded)" in source
    assert "Measured (published)" in source
    assert "estimates, not measurements" in source


def test_the_page_states_what_the_score_cannot_tell_you():
    """Discrimination is measurable on the held-out edition; calibration for
    years that were never recorded is not, and the page has to say so."""
    source = open("pages/retraction.py").read()
    assert "cannot" in source and "validate the absolute level" in source


def test_the_dashboard_still_imports_no_ml_stack():
    """The page reads rows from Postgres. If it ever imports rdl/ or torch,
    a multi-gigabyte dependency has entered the web process."""
    out = subprocess.run(
        [sys.executable, "-c",
         "import app, sys;"
         "bad=[m for m in ('torch','relbench','torch_geometric','torch_frame','rdl')"
         " if m in sys.modules];"
         "assert not bad, bad; print('clean')"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout


def test_an_author_history_is_resolved_by_id_not_by_name_string():
    """John Ioannidis is published as 'Ioannidis, John P.A.' in seven
    editions and 'Ioannidis, John Pa' in 2022. Matching the raw string
    silently dropped that year from his history."""
    from citations_lib.utils import retraction_for_author
    rows = retraction_for_author('Ioannidis, John P.A.', 'retraction_exposed')
    years = {r['data_year'] for r in rows}
    assert 2022 in years, f"2022 missing from {sorted(years)}"
    assert len(years) == 8


def test_measured_years_are_exactly_the_tracked_ones():
    from citations_lib.utils import retraction_by_edition
    rows = retraction_by_edition('retraction_exposed')
    measured = {r['data_year'] for r in rows if r['measured']}
    estimated = {r['data_year'] for r in rows if not r['measured']}
    assert measured == {2023, 2024}
    assert estimated == {2017, 2018, 2019, 2020, 2021, 2022}
    assert not (measured & estimated)


def test_publishing_refuses_a_run_with_no_evaluation():
    from rdl.publish import validate
    with pytest.raises(ValueError, match="metrics"):
        validate({"task": "x", "metrics": {}, "baseline": {}})
    with pytest.raises(ValueError, match="baseline"):
        validate({"task": "x", "metrics": {"roc_auc": 0.9}})


def test_the_page_says_what_the_column_actually_counts():
    """nc_rw counts citations RECEIVED where the CITING paper was retracted.
    Calling that "exposure" without unpacking it invites a reader to think a
    listed researcher retracted something, which the data does not say and
    which np_rw records separately. 71 to 76% have a non-zero value; framed
    carelessly that reads as an accusation against three quarters of the
    field."""
    source = open("pages/retraction.py").read()
    assert 'by any author' in source
    assert 'not** a measure of their own conduct' in source
    assert 'np_rw' in source and 'nc_to_rw' in source


def test_no_chart_label_calls_a_researcher_exposed():
    """The axis and hover text are what a reader screenshots, so they carry
    the careful wording rather than the shorthand."""
    import app  # noqa: F401
    import pages.retraction as retraction
    figure = retraction._overview_figure()
    assert 'retracted paper' in figure.layout.yaxis.title.text
    for trace in figure.data:
        assert 'exposed<' not in (trace.hovertemplate or '')
