"""One display name, one researcher's record.

113,478 display names belong to more than one author_id. Most of those are
different people who share a name ("Wang, Wei" is 26 researchers in
career-2024 alone), and reading a name used to take each edition from
whichever of them came first, so one career history was stitched together
from several people. Some are one person with a career id and a separate
single-year id, and those are read together when the two agree on the
institution in every year they share.
"""
import pytest

from citations_lib.utils import (
    _fetch,
    es_result_pick,
    get_es_results,
    one_researcher,
    score_standing,
)

MANY_PEOPLE = "Wang, Wei"
# One career-only author_id and one single-year-only author_id under each of
# these names. Identity resolution never matches across kinds, so a person
# can end up with one id per table.
#
# The same institution in every year both have a row: the same person.
SPLIT_IN_TWO = "Abbas, Mujahid"
# A different institution in every shared year: not shown as one person.
SPLIT_BUT_DISAGREE = "Baker, R. Jacob"
# No year in common, so nothing to compare: not shown as one person.
SPLIT_NO_OVERLAP = "Bachevalier, Jocelyne"


def _ids(name):
    return [row[0] for row in _fetch(
        "select author_id from authors where authfull_display = %s", (name,))]


def _owners(name, edition_id, nc):
    """The author_ids under `name` whose row in `edition_id` has this nc."""
    return {row[0] for row in _fetch(
        "select m.author_id from career_metrics m "
        "join authors a using (author_id) "
        "where a.authfull_display = %s and m.edition_id = %s and m.nc = %s",
        (name, edition_id, nc))}


def test_a_shared_name_reads_one_researchers_career():
    result = get_es_results(MANY_PEOPLE, "career", "authfull", exact=True)
    data = es_result_pick(result, "data", None)
    editions = [k for k in data if k.startswith("career_")
                and not k.endswith("_log")]
    assert len(editions) > 1
    common = None
    for key in editions:
        owners = _owners(MANY_PEOPLE, key.replace("_", "-"), data[key]["nc"])
        common = owners if common is None else common & owners
    assert common, "the career editions came from more than one author_id"


def test_the_same_researcher_is_chosen_whichever_kind_is_asked_for():
    career = es_result_pick(
        get_es_results(MANY_PEOPLE, "career", "authfull", exact=True),
        "data", None)
    both = es_result_pick(
        get_es_results(MANY_PEOPLE, ["career", "singleyr"], "authfull",
                       exact=True),
        "data", None)
    career_only = {k: v for k, v in both.items() if k.startswith("career_")}
    assert career == career_only


def test_one_researcher_picks_one_id_per_kind_for_different_people():
    chosen = one_researcher(tuple(_ids(MANY_PEOPLE)))
    assert set(chosen) <= {"career", "singleyr"}
    assert "career" in chosen
    assert isinstance(chosen["career"], str)


def test_a_missing_kind_is_not_guessed_from_several_people():
    # The chosen "Wang, Wei" has career rows only, and many single-year-only
    # ids share the name. Any one of them could be this researcher's other
    # half, or none of them, so none is taken.
    ids = _ids(MANY_PEOPLE)
    single_only = _fetch(
        "select count(distinct s.author_id) from singleyr_metrics s "
        "where s.author_id = any(%s) and not exists ("
        "  select 1 from career_metrics c where c.author_id = s.author_id)",
        (ids,))[0][0]
    assert single_only > 1
    chosen = one_researcher(tuple(ids))
    assert "singleyr" not in chosen


def test_the_exact_lookup_only_offers_the_kinds_the_chosen_researcher_has():
    # The career/single-year toggle is enabled from this frame. Offering
    # single-year for a researcher whose record has none leads to a lookup
    # that returns nothing.
    result = get_es_results(MANY_PEOPLE, ["career", "singleyr"], "authfull",
                            exact=True)
    chosen = one_researcher(tuple(sorted(_ids(MANY_PEOPLE))))
    assert set(result["_index"]) == set(chosen)
    for kind, author_id in chosen.items():
        assert set(result[result["_index"] == kind]["_source.author_id"]) \
            == {author_id}


def test_the_two_halves_of_a_split_researcher_are_read_together():
    chosen = one_researcher(tuple(_ids(SPLIT_IN_TWO)))
    assert set(chosen) == {"career", "singleyr"}
    assert chosen["career"] != chosen["singleyr"]
    data = es_result_pick(
        get_es_results(SPLIT_IN_TWO, ["career", "singleyr"], "authfull",
                       exact=True),
        "data", None)
    assert any(k.startswith("career_") for k in data)
    assert any(k.startswith("singleyr_") for k in data)


@pytest.mark.parametrize("name", [SPLIT_BUT_DISAGREE, SPLIT_NO_OVERLAP])
def test_a_split_pair_is_only_joined_when_the_institutions_agree(name):
    chosen = one_researcher(tuple(sorted(_ids(name))))
    assert len(chosen) == 1, chosen


# ------------------------------------------------------------- what-if rank

def test_a_score_below_everyone_published_has_no_scopus_rank():
    standing = score_standing("career", 2024, 0.01)
    assert standing["within_list"] == standing["published"] + 1
    assert standing["scopus_rank"] is None


def test_a_score_above_everyone_published_is_first():
    standing = score_standing("career", 2024, 1000.0)
    assert standing["within_list"] == 1
    assert standing["scopus_rank"] == 1


def _text(component):
    """Every string inside a Dash component tree, joined."""
    if isinstance(component, (list, tuple)):
        return " ".join(_text(c) for c in component)
    if isinstance(component, str):
        return component
    return _text(getattr(component, "children", None) or [])


def test_a_score_below_the_list_is_not_described_as_on_it():
    from citations_lib.auth_find import rank_stats
    text = _text(rank_stats(None, 230334, 230333, whatif=True))
    assert "on this list" not in text
    assert "below all 230,333 published" in text


def test_the_published_line_survives_a_missing_scopus_rank():
    from citations_lib.auth_find import rank_stats
    text = _text(rank_stats(5, 4, 100, whatif=True,
                            was={"list_rank": 3, "scopus_rank": None}))
    assert "published:" in text
