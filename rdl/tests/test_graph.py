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


def test_a_task_graph_does_not_contain_the_label_column():
    """Dataset.get_db does NOT apply remove_columns; only BaseTask.get_db
    does. Building from the dataset would put nc_rw into the graph as a
    feature while it is also the label, which scores beautifully and means
    nothing. This is the guard on that."""
    import pathlib
    pytest.importorskip("relbench.load")
    if not pathlib.Path("data_rdl/twopercenters/tasks/retraction_exposed"
                        "/manifest.yaml").exists():
        pytest.skip("run `python -m rdl.tasks.retraction` first")

    from relbench.load import load_dataset
    dataset = load_dataset("data_rdl/twopercenters")
    task = dataset.load_task("retraction_exposed")

    db = task.get_db(upto_test_timestamp=False)
    columns = set(db.table_dict["career_metrics"].df.columns)
    for hidden in ("nc_rw", "np_rw", "nc_to_rw"):
        assert hidden not in columns, f"{hidden} is visible to the model"

    # and the dataset view still has them, which is what makes the
    # distinction load-bearing rather than incidental
    plain = dataset.get_db(upto_test_timestamp=False)
    assert "nc_rw" in set(plain.table_dict["career_metrics"].df.columns)
