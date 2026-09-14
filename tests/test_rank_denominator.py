"""The rank shown to a reader must have a denominator that is true.

`rank` in this data is the position in a ranking of every scientist Scopus
scored, not of the people on the published list. Pairing it with the
edition's size produces a statement that cannot be true, and it is the first
thing a reader notices.
"""
import pandas as pd
import pytest

PARQUET = "data_parquet_v2/career_metrics.parquet"


def _edition(name="career-2024"):
    df = pd.read_parquet(PARQUET, columns=[
        "edition_id", "rank", "rank_subfield", "subfield_count", "c"])
    df = df[df.edition_id == name].copy()
    for col in ("rank", "rank_subfield", "subfield_count", "c"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def test_global_rank_exceeds_the_published_list_size():
    """The fact that makes the edition size the wrong denominator."""
    df = _edition()
    assert df["rank"].max() > len(df)
    assert (df["rank"] > len(df)).sum() > 40_000


def test_rank_is_a_strict_global_ordering_by_composite_score():
    """Which is why the denominator is the scored population, not the list:
    sorting by rank leaves c non-increasing."""
    df = _edition().dropna(subset=["rank", "c"]).sort_values("rank")
    assert (df["c"].diff().dropna() <= 1e-9).all()


def test_the_subfield_pair_is_internally_consistent():
    """Unlike the global one, this denominator is real."""
    df = _edition().dropna(subset=["rank_subfield", "subfield_count"])
    assert len(df) > 0
    assert (df["rank_subfield"] <= df["subfield_count"]).all()


def test_everyone_published_is_near_the_top_of_their_subfield():
    """Which is the reason a large global rank is not a contradiction."""
    df = _edition().dropna(subset=["rank_subfield", "subfield_count"])
    ratio = df["rank_subfield"] / df["subfield_count"]
    assert ratio.max() < 0.1


def test_the_author_panel_does_not_pair_rank_with_the_edition_size():
    """Regression guard on the wording itself: the panel used to say
    'Ranked among: 230,333 researchers' beside a rank of 1,210,493."""
    source = open("citations_lib/auth_find.py").read()
    assert "Ranked among:" not in source
    assert "Subfield standing:" in source
