"""The within-block matcher that replaces the per-edition ordinal."""
import pytest

from pipeline.matching import Candidate, DEFAULT_THRESHOLD, chain, pair_cost


def obs(key, year, score, h, *, kind="career", field="F1", subfield="S1",
        country="usa", institution="Inst"):
    return Candidate(key=key, edition_id=f"{kind}-{year}", kind=kind,
                     year=year, score=score, h=h, field=field,
                     subfield=subfield, country=country,
                     institution=institution)


def test_a_single_person_chains_across_every_edition():
    """c drifts slightly and h rises by one a year, which is the median
    behaviour measured over 957,429 real consecutive observations."""
    people = [obs(f"y{y}", y, 3.50 + 0.01 * (y - 2017), 20 + (y - 2017))
              for y in range(2017, 2025)]
    result = chain(people)
    assert len(result) == 1
    assert result[0] == [f"y{y}" for y in range(2017, 2025)]


def test_two_people_in_one_edition_never_merge():
    """Rule one, and the reason the ambiguous branch existed at all."""
    result = chain([obs("a", 2023, 3.5, 20), obs("b", 2023, 3.5, 20)])
    assert len(result) == 2
    assert sorted(len(c) for c in result) == [1, 1]


def test_a_block_of_five_is_pulled_apart_correctly():
    """Five people with distinct scores, each continuing into the next
    edition. The matcher has to pair them by career, not by order."""
    scores = [1.5, 2.5, 3.5, 4.5, 5.5]
    first = [obs(f"a{i}", 2023, s, 10 + i) for i, s in enumerate(scores)]
    # deliberately shuffled, and each score nudged as a real one would be
    second = [obs(f"b{i}", 2024, s + 0.01, 11 + i)
              for i, s in reversed(list(enumerate(scores)))]
    result = chain(first + second)
    assert len(result) == 5
    for c in result:
        assert len(c) == 2
        i = c[0][1:]
        assert c[1] == f"b{i}", f"{c[0]} was matched to {c[1]}"


def test_a_departure_leaves_its_chain_alone():
    """Someone who leaves must not be forced onto a newcomer."""
    result = chain([
        obs("stays_23", 2023, 3.5, 20), obs("leaves_23", 2023, 9.9, 60),
        obs("stays_24", 2024, 3.51, 21),
    ])
    chains = {c[0]: c for c in result}
    assert chains["stays_23"] == ["stays_23", "stays_24"]
    assert chains["leaves_23"] == ["leaves_23"]


def test_an_arrival_starts_its_own_chain():
    result = chain([
        obs("old_23", 2023, 3.5, 20),
        obs("old_24", 2024, 3.51, 21), obs("new_24", 2024, 8.0, 55),
    ])
    chains = {c[0]: c for c in result}
    assert chains["old_23"] == ["old_23", "old_24"]
    assert chains["new_24"] == ["new_24"]


def test_a_wildly_different_career_is_refused_even_when_alone():
    """With only one candidate on each side the assignment would happily
    pair them. The threshold is what stops it."""
    result = chain([obs("a", 2023, 1.0, 5), obs("b", 2024, 90.0, 300)])
    assert len(result) == 2


def test_career_and_singleyr_never_match_each_other():
    """c means a different quantity in each table, so they are separate
    timelines even for the same person."""
    result = chain([obs("career", 2023, 3.5, 20, kind="career"),
                    obs("single", 2023, 3.5, 20, kind="singleyr")])
    assert len(result) == 2


def test_a_gap_year_is_survivable():
    """Absence from one edition must not permanently end a chain: people
    drop off the list and come back."""
    result = chain([obs("a", 2022, 3.50, 20), obs("a24", 2024, 3.52, 22)])
    assert len(result) == 1
    assert result[0] == ["a", "a24"]


def test_result_does_not_depend_on_input_order():
    people = [obs(f"a{i}", 2023, 1.0 + i, 10 + i) for i in range(4)]
    people += [obs(f"b{i}", 2024, 1.01 + i, 11 + i) for i in range(4)]
    first = chain(people)
    second = chain(list(reversed(people)))
    assert sorted(map(tuple, first)) == sorted(map(tuple, second))


def test_h_going_backwards_is_penalised():
    """h is non-decreasing for a real person in 98.8% of steps."""
    forward = pair_cost(obs("a", 2023, 3.5, 20), obs("b", 2024, 3.5, 22))
    backward = pair_cost(obs("a", 2023, 3.5, 20), obs("b", 2024, 3.5, 18))
    assert backward > forward


def test_a_changed_institution_costs_less_than_a_changed_country():
    """Institution holds in only 72.3% of steps and country in 97.3%, so a
    moved institution is weak evidence and a changed country is strong."""
    base = obs("a", 2023, 3.5, 20)
    moved = pair_cost(base, obs("b", 2024, 3.5, 20, institution="Other"))
    emigrated = pair_cost(base, obs("b", 2024, 3.5, 20, country="gbr"))
    assert moved < emigrated


def test_a_missing_attribute_sits_between_agreement_and_disagreement():
    """Charging nothing for an absent value would make it exactly as good as
    agreement, so a row with gaps would beat a row that genuinely matches.
    Thomas, Stephen J. in career-2019 has no country and, at zero, cost 2.607
    against 2.868 for the real continuation of the 2018 row: the career went
    to the wrong person."""
    base = obs("a", 2023, 3.5, 20)
    agrees = pair_cost(base, obs("b", 2024, 3.5, 20))
    absent = pair_cost(base, obs("b", 2024, 3.5, 20, country=None))
    disagrees = pair_cost(base, obs("b", 2024, 3.5, 20, country="gbr"))
    assert agrees < absent < disagrees


def test_a_row_with_gaps_does_not_outrank_a_row_that_matches():
    """The regression in its own terms: given a real continuation and an
    impostor whose attributes are simply absent, the continuation must win."""
    previous = obs("prev", 2023, 3.52, 37, country="gbr", subfield="S1")
    real = obs("real", 2024, 3.67, 38, country="gbr", subfield="S2")
    impostor = obs("gap", 2024, 3.40, 40, country=None, subfield="S3")
    assert pair_cost(previous, real) < pair_cost(previous, impostor)


def test_a_continuation_costs_less_than_the_threshold():
    """A real continuation that also changed institution and subfield must
    still be accepted."""
    cost = pair_cost(obs("a", 2023, 3.50, 20),
                     obs("b", 2024, 3.52, 21,
                         institution="Elsewhere", subfield="S2"))
    assert cost < DEFAULT_THRESHOLD


def test_an_unrelated_person_costs_more_than_the_threshold():
    cost = pair_cost(obs("a", 2023, 3.5, 20), obs("b", 2024, 4.5, 40))
    assert cost > DEFAULT_THRESHOLD


def test_empty_input_is_not_an_error():
    assert chain([]) == []
