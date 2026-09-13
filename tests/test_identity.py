import random

from pipeline.identity import normalize, block_key, resolve


def test_block_key_is_stable_across_given_name_expansion():
    # The 2023 -> 2024 break: Scopus expanded abbreviated preferred names.
    assert block_key("Severinghaus, J. W.") == block_key("Severinghaus, John Wendell")
    assert block_key("Cotran, Ramzi") == block_key("Cotran, Ramzi S.")
    assert block_key("Dahmen, U.") == block_key("Dahmen, Ulrich")


def test_block_key_separates_different_people():
    assert block_key("Dahmen, Karin A.") != block_key("Dahmen, Ulrich")


def test_normalize_folds_accents():
    assert normalize("Grätzel, Michael") == normalize("Gratzel, Michael")


def test_block_key_keeps_compound_surname_intact():
    # R3: normalize() strips the comma that separates surname from given name,
    # so splitting on a space AFTER normalizing wrongly treats "van" as the
    # surname and "der" as the initial source for compound surnames. The raw
    # name must be split on the comma first, then each side normalized.
    assert block_key("van der Berg, Jan") == block_key("van der Berg, J.")
    surname, initial = block_key("van der Berg, Jan")
    assert surname == "van der berg"
    assert initial == "j"


def test_same_person_across_editions_gets_one_id():
    observations = [
        {"edition_id": "career_2023", "authfull": "Severinghaus, J. W.",
         "firstyr": 1958, "inst_name": "UCSF", "cntry": "usa"},
        {"edition_id": "career_2024", "authfull": "Severinghaus, John Wendell",
         "firstyr": 1958, "inst_name": "UCSF", "cntry": "usa"},
    ]
    resolutions = resolve(observations)
    assert len({r.author_id for r in resolutions}) == 1
    assert all(r.is_confident for r in resolutions)


def test_two_people_in_one_edition_are_never_merged():
    # Each edition lists each author exactly once, so two rows in the same
    # edition are two different humans by construction.
    observations = [
        {"edition_id": "career_2021", "authfull": "Abraham, Edward",
         "firstyr": 1975, "inst_name": "University of Miami", "cntry": "usa"},
        {"edition_id": "career_2021", "authfull": "Abraham, Edward",
         "firstyr": 1975, "inst_name": "Dragonfly Data Science", "cntry": "nzl"},
    ]
    resolutions = resolve(observations)
    assert len({r.author_id for r in resolutions}) == 2
    assert not any(r.is_confident for r in resolutions)


def test_same_edition_collision_with_identical_institution_still_splits():
    # Two rows, same edition, same surname/initial/firstyr AND same inst_name.
    # Rule 1 is absolute: they must still get distinct author_ids.
    observations = [
        {"edition_id": "career_2021", "authfull": "Abraham, Edward",
         "firstyr": 1975, "inst_name": "University of Miami", "cntry": "usa"},
        {"edition_id": "career_2021", "authfull": "Abraham, Edward",
         "firstyr": 1975, "inst_name": "University of Miami", "cntry": "usa"},
    ]
    resolutions = resolve(observations)
    assert len({r.author_id for r in resolutions}) == 2
    assert not any(r.is_confident for r in resolutions)


def test_same_edition_collision_with_missing_institution_still_splits():
    # Two rows, same edition, same surname/initial/firstyr, inst_name missing
    # on both. The naive discriminator normalize(None or "") == "" for both,
    # which would collide; the ordinal-based fallback must still split them.
    observations = [
        {"edition_id": "career_2021", "authfull": "Abraham, Edward",
         "firstyr": 1975, "inst_name": None, "cntry": None},
        {"edition_id": "career_2021", "authfull": "Abraham, Edward",
         "firstyr": 1975, "inst_name": None, "cntry": None},
    ]
    resolutions = resolve(observations)
    assert len({r.author_id for r in resolutions}) == 2
    assert not any(r.is_confident for r in resolutions)


def test_nothing_is_dropped():
    observations = [
        {"edition_id": "career_2021", "authfull": "Abe, Hiroshi",
         "firstyr": 1990, "inst_name": "Fukuoka University", "cntry": "jpn"},
        {"edition_id": "career_2021", "authfull": "Abe, Hiroshi",
         "firstyr": 1985, "inst_name": "Riken", "cntry": "jpn"},
        {"edition_id": "career_2022", "authfull": "Abe, Hiroshi",
         "firstyr": 1990, "inst_name": "Fukuoka University", "cntry": "jpn"},
    ]
    assert len(resolve(observations)) == 3


def test_author_ids_are_deterministic():
    # A pure function trivially returns the same thing twice on the same
    # input; that proves nothing. Determinism means the input's ORDER must
    # not matter. Build a batch that mixes confident and ambiguous groups,
    # resolve it, shuffle it with a fixed seed, resolve it again, and check
    # that the mapping from (edition_id, authfull) to author_id is identical.
    observations = [
        {"edition_id": "career_2024", "authfull": "Wang, Zhong Lin",
         "firstyr": 1986, "inst_name": "Georgia Tech", "cntry": "usa"},
        {"edition_id": "career_2023", "authfull": "Wang, Z. L.",
         "firstyr": 1986, "inst_name": "Georgia Tech", "cntry": "usa"},
        {"edition_id": "career_2021", "authfull": "Abraham, Edward",
         "firstyr": 1975, "inst_name": "University of Miami", "cntry": "usa"},
        {"edition_id": "career_2021", "authfull": "Abraham, Ed",
         "firstyr": 1975, "inst_name": "Dragonfly Data Science", "cntry": "nzl"},
        {"edition_id": "career_2021", "authfull": "Abraham, E.",
         "firstyr": 1975, "inst_name": None, "cntry": None},
    ]
    # The three "Abraham" rows share a block key (surname "abraham", initial
    # "e") and firstyr, so they land in the same ambiguous group, but each has
    # a distinct authfull, so (edition_id, authfull) is still a unique key to
    # check the mapping against.

    def mapping(obs_list):
        return {(r.edition_id, r.authfull): r.author_id for r in resolve(obs_list)}

    first = mapping(observations)

    shuffled = observations[:]
    random.Random(42).shuffle(shuffled)
    second = mapping(shuffled)

    assert first == second
