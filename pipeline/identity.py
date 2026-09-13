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


@dataclass(frozen=True)
class Resolution:
    author_id: str
    edition_id: str
    authfull: str
    method: str
    is_confident: bool


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
                    ))
                continue

            # Fall back to institution as a tiebreaker, and keep every row as its
            # own author when even that fails. Never merge, never drop.
            for obs in group:
                discriminator = normalize(obs.get("inst_name") or "")
                resolutions.append(Resolution(
                    author_id=_author_id(surname, initial, firstyr, discriminator),
                    edition_id=obs["edition_id"],
                    authfull=obs["authfull"],
                    method="surname_initial_firstyr_institution",
                    is_confident=False,
                ))

    return resolutions
