import pytest

from rdl import graph, spec


def _st(name):
    from torch_frame import stype
    return stype[name]


def test_pinned_stypes_override_the_proposal():
    """get_stype_proposal infers from dtype and cardinality, which labels
    firstyr (a year, ~60 distinct values) categorical. That would turn a
    regression into a sixty-way classification and discard the ordering."""
    proposed = {"career_metrics": {"firstyr": _st("categorical"),
                                   "c": _st("numerical")}}
    merged = graph.apply_pins(proposed)
    assert merged["career_metrics"]["firstyr"] == _st("numerical")
    assert merged["career_metrics"]["c"] == _st("numerical")


def test_dropped_columns_never_reach_the_graph():
    proposed = {"career_metrics": {c: _st("numerical")
                                   for c in spec.NS_COLUMNS + ["c"]}}
    merged = graph.apply_pins(proposed)
    assert not [c for c in merged["career_metrics"] if c.endswith("_ns")]
    assert "c" in merged["career_metrics"]


def test_identity_columns_are_removed_by_the_pins():
    proposed = {"authors": {"authfull_display": _st("categorical"),
                            "firstyr": _st("categorical")},
                "institutions": {"inst_name": _st("categorical")}}
    merged = graph.apply_pins(proposed)
    assert "authfull_display" not in merged["authors"]
    assert "inst_name" not in merged["institutions"]


def test_unknown_columns_keep_their_proposal():
    """A column we have not thought about should get a sensible default,
    not vanish."""
    proposed = {"career_metrics": {"something_new": _st("numerical")}}
    merged = graph.apply_pins(proposed)
    assert merged["career_metrics"]["something_new"] == _st("numerical")


def test_a_table_we_do_not_declare_passes_through_untouched():
    proposed = {"openalex_authors": {"orcid": _st("categorical")}}
    merged = graph.apply_pins(proposed)
    assert merged["openalex_authors"]["orcid"] == _st("categorical")
