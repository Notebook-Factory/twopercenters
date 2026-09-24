"""Link one person's observations across editions when the name cannot.

This exists because the previous approach could not. When a
`(surname, first initial, firstyr)` block holds more than one person, the old
resolver gave every observation its own identity, minted per edition. That
kept two people in one edition apart, which is correct and non-negotiable,
but it also guaranteed the same person got a different identity in the next
edition. Measured over the whole dataset: authors flagged ambiguous averaged
1.00 editions each and 100% of them appeared exactly once, against 4.44 and
23.6% for everyone else. 132,313 career rows, 9.4% of the table, could not
have a time series at all.

The fix is to stop guessing from the name and start matching on the career.
Measured over 957,429 consecutive-edition observations of authors the
resolver already trusted:

    composite score c   median change 0.42% per year, 90th pct 4.21%
    h-index             never decreases in 98.8% of steps, median +1
    paper count np      never decreases in 92.0%
    field               unchanged 97.9%
    country             unchanged 97.3%
    subfield            unchanged 96.3%
    institution         unchanged 72.3%

A composite score that moves less than half a percent a year is close to a
fingerprint. Framed as an assignment problem inside a block, and tested
against blocks whose members share firstyr, field AND country so that none of
those can discriminate, this recovers 99.4% of true pairings at block size 50
where chance is 2%.

Two properties the implementation has to keep.

**Two rows in one edition are two different people.** The assignment is
one-to-one, so this holds by construction rather than by a check.

**A person who genuinely left must not be forced onto a newcomer.** Blocks
gain and lose members, so the assignment is rectangular and every pairing
above `threshold` is rejected. A rejected pairing leaves both sides
unmatched: the older chain simply ends, and the newer observation starts a
new one.

Matching runs within one kind of edition. `c` and `h` mean different
quantities in the career and single-year tables, so a career observation and
a single-year observation are never candidates for each other.
"""
from __future__ import annotations

from dataclasses import dataclass

# Weights validated in docs/identity-resolution-findings.md. The relative
# change in c dominates deliberately: it is the strongest single signal, and
# the categorical attributes are there to break ties it cannot.
W_SCORE = 40.0
W_H_REGRESS = 1.0      # h going down at all is suspicious
W_H_DRIFT = 1.0 / 20.0  # and going up a lot is mildly so
W_FIELD = 1.5
W_SUBFIELD = 0.8
W_COUNTRY = 1.2
W_INSTITUTION = 0.3

# A pairing costing more than this is refused. 6.0 sits well above what a
# genuine continuation costs (a changed institution and subfield together
# come to 1.1) and well below an unrelated person's, which the c term alone
# pushes past 10 as soon as the scores differ by 25%.
DEFAULT_THRESHOLD = 6.0

# What an absent attribute costs, as a fraction of what a mismatch costs.
# Not zero: see pair_cost.
MISSING_FRACTION = 0.5


@dataclass(frozen=True)
class Candidate:
    """One observation, reduced to what matching needs."""

    key: object            # whatever the caller uses to identify the row
    edition_id: str
    kind: str
    year: int
    score: float | None    # c
    h: float | None
    field: str | None
    subfield: str | None
    country: str | None
    institution: str | None


def pair_cost(previous: Candidate, nxt: Candidate) -> float:
    """What it costs to claim these two observations are the same person.

    A missing attribute is charged half of what a mismatch costs. Charging
    nothing looks like the neutral choice and is not: a match costs nothing
    too, so an absent value would be exactly as good as agreement, and a row
    with gaps would beat a row that genuinely matches. That is not
    hypothetical. `Thomas, Stephen J.` in career-2019 has no country, and
    with missing charged at zero he cost 2.607 against 2.868 for
    `Thomas, S. H.L.`, the real continuation of the 2018 row, so the 2018
    career was handed to the wrong person. Given a country he costs 3.807 and
    loses, correctly.

    Half the weight puts an absent value between agreement and disagreement,
    which is what "no evidence" should mean.
    """
    cost = 0.0

    if previous.score is not None and nxt.score is not None:
        denominator = max(abs(previous.score), 1e-6)
        cost += W_SCORE * abs(nxt.score - previous.score) / denominator
    else:
        # Without the strongest signal, hold the pairing to a stricter
        # standard on the rest rather than letting it through cheaply.
        cost += 2.0

    if previous.h is not None and nxt.h is not None:
        delta = nxt.h - previous.h
        if delta < 0:
            cost += W_H_REGRESS * min(abs(delta), 10)
        cost += W_H_DRIFT * abs(delta)

    for attribute, weight in (("field", W_FIELD), ("subfield", W_SUBFIELD),
                              ("country", W_COUNTRY),
                              ("institution", W_INSTITUTION)):
        a = getattr(previous, attribute)
        b = getattr(nxt, attribute)
        if a is None or b is None:
            cost += weight * MISSING_FRACTION
        elif a != b:
            cost += weight

    return cost


def _assign(previous: list[Candidate], nxt: list[Candidate],
            threshold: float) -> dict[int, int]:
    """Rectangular one-to-one assignment. Returns {next index: prev index}.

    Uses scipy when it is available and falls back to a greedy pass over the
    cheapest pairings otherwise, so the pipeline does not gain a hard
    dependency on scipy for a path that is only taken inside ambiguous
    blocks.
    """
    costs = [[pair_cost(p, n) for n in nxt] for p in previous]

    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment
    except ImportError:
        return _assign_greedy(costs, threshold)

    if not costs or not costs[0]:
        return {}
    matrix = np.asarray(costs, dtype=float)
    # Refused pairings must not merely be expensive: make them unchoosable,
    # so the solver never trades a good pair away to place a bad one.
    matrix = np.where(matrix > threshold, 1e9, matrix)
    rows, cols = linear_sum_assignment(matrix)
    return {int(c): int(r) for r, c in zip(rows, cols)
            if matrix[r, c] < 1e9}


def _assign_greedy(costs, threshold: float) -> dict[int, int]:
    pairs = sorted(
        ((cost, r, c) for r, row in enumerate(costs)
         for c, cost in enumerate(row) if cost <= threshold),
        key=lambda t: (t[0], t[1], t[2]))
    taken_rows: set[int] = set()
    taken_cols: set[int] = set()
    out: dict[int, int] = {}
    for cost, r, c in pairs:
        if r in taken_rows or c in taken_cols:
            continue
        taken_rows.add(r)
        taken_cols.add(c)
        out[c] = r
    return out


def chain(candidates: list[Candidate],
          threshold: float = DEFAULT_THRESHOLD) -> list[list[object]]:
    """Group observations into one chain per person.

    Returns a list of chains, each a list of the caller's keys in edition
    order. Deterministic: candidates are ordered by (year, kind, key) before
    matching, so the result does not depend on input order.
    """
    if not candidates:
        return []

    chains: list[list[object]] = []
    # Where each live chain currently ends, per kind. A chain is only ever
    # extended by an observation of its own kind.
    tips: dict[str, list[tuple[Candidate, int]]] = {}

    ordered = sorted(candidates, key=lambda c: (c.year, c.kind, str(c.key)))
    steps: list[tuple[tuple[int, str], list[Candidate]]] = []
    for candidate in ordered:
        step = (candidate.year, candidate.kind)
        if steps and steps[-1][0] == step:
            steps[-1][1].append(candidate)
        else:
            steps.append((step, [candidate]))

    for (_year, kind), group in steps:
        live = tips.get(kind, [])
        if not live:
            for candidate in group:
                chains.append([candidate.key])
                tips.setdefault(kind, []).append((candidate, len(chains) - 1))
            continue

        assignment = _assign([c for c, _ in live], group, threshold)
        new_tips: list[tuple[Candidate, int]] = []
        matched_chain_indices = set()

        for index, candidate in enumerate(group):
            if index in assignment:
                _, chain_index = live[assignment[index]]
                chains[chain_index].append(candidate.key)
                new_tips.append((candidate, chain_index))
                matched_chain_indices.add(assignment[index])
            else:
                chains.append([candidate.key])
                new_tips.append((candidate, len(chains) - 1))

        # A chain nobody continued is not dead: the person may simply be
        # absent for one edition and return. Keep its tip so a later edition
        # can still claim it.
        for position, (candidate, chain_index) in enumerate(live):
            if position not in matched_chain_indices:
                new_tips.append((candidate, chain_index))

        tips[kind] = new_tips

    return chains
