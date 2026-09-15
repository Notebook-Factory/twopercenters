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


def test_a_recorded_year_reports_the_magnitude_not_just_the_word():
    """"recorded" alone says nothing. The bar label carries the share of the
    author's citations that came from retracted papers, and the count."""
    import app  # noqa: F401
    import pages.retraction as retraction
    figure = retraction._author_panel('Ioannidis, John P.A.').children[0].figure
    recorded = [t for t in figure.data if 'Recorded' in (t.name or '')]
    assert recorded, [t.name for t in figure.data]
    labels = ' '.join(recorded[0].text)
    assert '% of cites' in labels
    assert 'recorded)' in labels


def test_the_measured_share_comes_from_the_data():
    """0.07% and 0.10% for Ioannidis in 2023 and 2024: 169 of 259,475 and
    278 of 284,984 citations."""
    from citations_lib.utils import retraction_for_author
    rows = {r['data_year']: r for r in
            retraction_for_author('Ioannidis, John P.A.', 'retraction_exposed')}
    assert rows[2023]['citations'] == 169
    assert rows[2024]['citations'] == 278
    assert 0.06 < rows[2023]['share'] < 0.08


def test_the_search_box_shows_who_is_being_displayed():
    """A Dash dropdown renders its label by looking the value up in options,
    so an empty options list showed the placeholder while a researcher was
    charted underneath it."""
    import app  # noqa: F401
    import pages.retraction as retraction

    found = []

    def walk(node):
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if getattr(node, '_prop_names', None) is None:
            return
        if getattr(node, 'id', None) == 'retraction-author':
            found.append(node)
        walk(getattr(node, 'children', None))

    walk(retraction.layout)
    assert found, 'the author dropdown is gone'
    dropdown = found[0]
    assert any(o['value'] == dropdown.value for o in dropdown.options)


def test_typing_does_not_drop_the_selected_name():
    import app  # noqa: F401
    import pages.retraction as retraction
    options = retraction._search('Zhu Jianguo Sydney', 'Ioannidis, John P.A.')
    assert any(o['value'] == 'Ioannidis, John P.A.' for o in options)


def test_escape_closes_rather_than_toggles():
    """Escape appeared dead because it was handled twice: dbc.Modal closes
    itself on Escape, and the handler then clicked the navbar Search button,
    which toggles, reopening the overlay in the same keystroke. Clicking the
    dedicated close button is idempotent."""
    source = open('assets/spotlight.js').read()
    escape_block = source[source.index("if (key === 'escape')"):]
    escape_block = escape_block[:escape_block.index('document.addEventListener')]
    assert "getElementById('spotlight-close')" in escape_block
    assert "getElementById('spotlight-open')" not in escape_block


def test_an_estimated_year_says_roughly_how_many_not_only_whether():
    """The binary model answers "was there any"; a second regression answers
    "how many". Only publishing the first left the estimated years saying
    "~100% likely" beside recorded years saying "278 recorded"."""
    import app  # noqa: F401
    import pages.retraction as retraction
    figure = retraction._author_panel('Ioannidis, John P.A.').children[0].figure
    estimated = [t for t in figure.data if 'Estimated' in (t.name or '')]
    assert estimated
    labels = ' '.join(estimated[0].text)
    assert 'likely' in labels and 'cites' in labels


def test_no_published_count_is_negative():
    """The regression head is unconstrained and produced negative counts for
    41% of rows. A count of citations cannot be negative."""
    from citations_lib.utils import _fetch
    worst = _fetch("select min(value) from predictions "
                   "where task = 'retraction_exposure'")[0][0]
    assert worst is not None and worst >= 0


def test_the_page_states_the_count_model_is_the_weaker_one():
    """Its mean error is 4.1 citations against a median true value of 2. A
    count shown without that reads as a measurement."""
    source = open('pages/retraction.py').read()
    assert '4.1 citations' in source
    assert 'band rather than a figure' in source


def test_the_population_view_reports_citation_counts_too():
    """"How many researchers" and "how many citations" are different
    questions and the page answers both."""
    from citations_lib.utils import retraction_counts_by_edition
    rows = retraction_counts_by_edition()
    years = {r['data_year'] for r in rows}
    assert years == set(range(2017, 2025))
    measured = {r['data_year'] for r in rows if r['measured']}
    assert measured == {2023, 2024}


def test_the_step_at_the_boundary_is_explained_not_left_hanging():
    """Estimated years average about 3 citations against 5.5 recorded in
    2023. A reader who takes that step as real concludes retractions doubled,
    when it is the regression pulling large values toward the middle."""
    source = open('pages/retraction.py').read()
    assert 'not' in source and 'retractions doubling in 2023' in source
    assert 'floor rather than a level' in source


def test_the_estimated_population_mean_is_below_the_measured_one():
    """The conservatism the caption describes, asserted against the data so
    the caption cannot quietly stop being true."""
    from citations_lib.utils import retraction_counts_by_edition
    rows = retraction_counts_by_edition()
    estimated = [r['mean'] for r in rows if not r['measured']]
    measured = [r['mean'] for r in rows if r['measured']]
    assert max(estimated) < min(measured)
