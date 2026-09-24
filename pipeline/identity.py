"""Resolve author identity across editions.

The source data carries no author identifier, only a formatted name string that
is the Scopus profile's preferred name at calculation time. Between the 2023 and
2024 editions 90,755 of those strings changed, because Scopus expanded
abbreviated given names, so exact-name matching links only 57.7 percent of
authors across that boundary against a 79-85 percent baseline elsewhere.

Blocking on surname plus first initial plus firstyr restores it to roughly 85
percent. firstyr is the right third component because it is a property of a
career rather than of current circumstances: it is identical for 94-97 percent
of exactly-matched names, where institution manages only 69-84 percent. Country
was measured and rejected, because researchers relocate and it costs matches.

Two rules are absolute. Two rows in the same edition are two different people and
must never merge. Nothing is ever dropped; what does not resolve becomes a
separate author flagged not-confident.

block_key must split the RAW name on the comma before normalizing either side.
normalize() strips punctuation, including the comma that separates surname from
given name, so normalizing first and then splitting on a space would treat
compound surnames ("van der Berg", "von Neumann", "de la Cruz", "Al-Amin") as
just their first token, with the rest of the surname misread as the given name.
Splitting on the comma first keeps the whole compound surname intact.
"""
import hashlib
import re
import unicodedata
from dataclasses import dataclass

from pipeline import matching


@dataclass(frozen=True)
class Resolution:
    author_id: str
    edition_id: str
    authfull: str
    method: str
    is_confident: bool
    # The `_token` of the observation this came from, when the caller set
    # one. Inside an ambiguous block several rows share an edition and a
    # name, so that pair is not enough to identify a row; the token is.
    token: object = None


def normalize(name):
    decomposed = unicodedata.normalize("NFKD", str(name))
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).strip()


def block_key(name):
    """(surname, first initial). Stable when a given name is expanded.

    Splits the raw name on the comma first, then normalizes each side
    separately, so a compound surname ("van der Berg") is never split apart
    by normalize()'s punctuation stripping.
    """
    surname_part, _, given_part = str(name).partition(",")
    surname = normalize(surname_part)
    given = normalize(given_part)
    given_parts = given.split()
    initial = given_parts[0][0] if given_parts else ""
    return surname, initial


def _author_id(surname, initial, firstyr, discriminator):
    raw = f"{surname}|{initial}|{firstyr}|{discriminator}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _ambiguous_author_id(surname, initial, firstyr, signature, ordinal):
    """An id for one person inside an ambiguous block.

    `signature` describes the chain itself, so the id follows the person
    rather than the edition. The ordinal only breaks ties between two chains
    that produced identical signatures, which is possible when two members
    of a block are genuinely indistinguishable on every attribute we hold.
    """
    raw = f"{surname}|{initial}|{firstyr}|{signature}|{ordinal}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class _Chain:
    signature: str
    order: tuple
    observations: list


def _candidate(obs, index):
    """Reduce an observation to what pipeline.matching needs.

    Observations that carry no metrics still match on their categorical
    attributes; the cost function treats a missing value as neither evidence
    for a pairing nor against it.
    """
    edition_id = str(obs["edition_id"])
    kind, _, year = edition_id.rpartition("-")
    try:
        year_value = int(year)
    except ValueError:
        year_value = 0
    return matching.Candidate(
        key=index,
        edition_id=edition_id,
        kind=kind or "unknown",
        year=year_value,
        score=_number(obs.get("c")),
        h=_number(obs.get("h")),
        field=_text(obs.get("field")),
        subfield=_text(obs.get("subfield")),
        country=_text(obs.get("cntry")),
        institution=_text(obs.get("inst_name")),
    )


def _number(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number      # NaN


def _text(value):
    if value is None:
        return None
    text = normalize(value)
    return text or None


def _chain_group(group):
    """Split one ambiguous firstyr group into one _Chain per person.

    The signature anchors on the chain's FIRST observation and nothing else,
    which is what keeps an author's id stable when the next edition arrives.
    Signing the whole chain would be stable across reruns but not across a
    reload: every ambiguous author's id would change the moment they gained
    an observation, which is exactly what this work exists to stop.

    Anchoring forward is safe because editions arrive in chronological order
    and `matching.chain` only ever looks backward, so a later edition cannot
    alter which observation starts a chain.
    """
    candidates = [_candidate(obs, index) for index, obs in enumerate(group)]
    chains = matching.chain(candidates)

    members = []
    for indices in chains:
        observations = sorted(
            (group[i] for i in indices),
            key=lambda o: (str(o["edition_id"]), str(o["authfull"])))
        first = observations[0]
        members.append(_Chain(
            signature=f"{first['edition_id']}:{normalize(first['authfull'])}",
            # Two chains can legitimately start at the same edition under the
            # same name: that is the same-edition case, two different people.
            # They are ordered by properties of their first observation only,
            # so the ordinal is as stable as the signature.
            order=(
                normalize(first.get("inst_name") or ""),
                normalize(first.get("cntry") or ""),
                _number(first.get("c")) if _number(first.get("c")) is not None else 0.0,
                str(first["authfull"]),
            ),
            observations=observations))

    members.sort(key=lambda m: (m.signature, m.order))

    # The ordinal counts only within a signature, so a chain's id does not
    # shift because some unrelated chain in the block appeared or vanished.
    numbered = []
    seen = {}
    for member in members:
        ordinal = seen.get(member.signature, 0)
        seen[member.signature] = ordinal + 1
        numbered.append((member, ordinal))
    return numbered


def resolve(observations):
    blocks = {}
    for obs in observations:
        surname, initial = block_key(obs["authfull"])
        blocks.setdefault((surname, initial), []).append(obs)

    resolutions = []
    for (surname, initial), members in blocks.items():
        by_firstyr = {}
        for obs in members:
            by_firstyr.setdefault(obs.get("firstyr"), []).append(obs)

        for firstyr, group in by_firstyr.items():
            editions = [o["edition_id"] for o in group]
            # One row per edition means one person. More than one row in any
            # single edition means the firstyr did not disambiguate them.
            ambiguous = len(editions) != len(set(editions))

            if not ambiguous:
                author_id = _author_id(surname, initial, firstyr, "")
                for obs in group:
                    resolutions.append(Resolution(
                        author_id=author_id,
                        edition_id=obs["edition_id"],
                        authfull=obs["authfull"],
                        method="surname_initial_firstyr",
                        is_confident=True,
                        token=obs.get("_token"),
                    ))
                continue

            # The firstyr block did not disambiguate this group: it contains
            # more than one row from at least one edition. Rule 1 (two rows in
            # the same edition are two different people) is absolute.
            #
            # An earlier version satisfied that rule by giving every
            # observation its own author_id, minted per edition. It did keep
            # same-edition rows apart, and it also guaranteed the same person
            # got a different id in the next edition, so nobody in an
            # ambiguous block ever had a time series: measured across the
            # whole dataset, those authors averaged 1.00 editions each and
            # 100% of them appeared exactly once.
            #
            # Now the block is matched on the career instead of the name.
            # pipeline.matching solves a rectangular assignment per edition
            # step, which enforces rule 1 by construction (one-to-one) and
            # refuses any pairing above its threshold, so someone who
            # genuinely left is not forced onto a newcomer.
            for member, ordinal in _chain_group(group):
                author_id = _ambiguous_author_id(
                    surname, initial, firstyr, member.signature, ordinal)
                for obs in member.observations:
                    resolutions.append(Resolution(
                        author_id=author_id,
                        edition_id=obs["edition_id"],
                        authfull=obs["authfull"],
                        method="career_matched",
                        is_confident=False,
                        token=obs.get("_token"),
                    ))

    return resolutions
