"""What each table means, relationally and semantically.

This is the single source of truth for both the RelBench dataset manifest and
the semantic-type dictionary the graph is built from. It is shaped like
``relbench.manifest.TableSpec`` (pkey, time_col, fkeys) plus the two things
that dataclass does not model: the columns we drop, and the semantic types we
pin rather than let be inferred.

Only the career editions are described here. Every task in the plan asks a
career question, and ``singleyr_metrics`` is a second 1.2 GB table that
answers none of them. ``author_name_observations`` is likewise out: it is the
name history, which matters to entity resolution, a question deferred to its
own plan.

Two of the pins are here because RelBench's own heuristic would get them
wrong, and getting them wrong is silent:

* ``firstyr`` and ``lastyr`` are years. Their cardinality is low enough that
  ``get_stype_proposal`` labels them categorical, which would turn a
  regression into a sixty-way classification.
* ``inst_name`` has 66,079 distinct values, too many to encode as a category,
  but the words in it ("University of", "Hospital", place names) carry real
  signal, so it is text.
"""
from dataclasses import dataclass, field

import pandas as pd

# The split boundaries, fixed for every task so results stay comparable.
# Training sees editions up to and including 2022, validation predicts the
# 2023 edition, test predicts 2024. The editions are annual and stamped
# 31 December of their data year.
VAL_TIMESTAMP = pd.Timestamp("2022-12-31")
TEST_TIMESTAMP = pd.Timestamp("2023-12-31")
TIMEDELTA = "365 days"

# The non-self-citation restatements. Each is the same metric recomputed with
# self-citations removed, so it correlates almost perfectly with its bare
# counterpart. Keeping them costs 185 MB and gives the model fifteen
# near-duplicate columns to spread attention over.
NS_COLUMNS = [
    "rank_ns", "c_ns", "h_ns", "hm_ns", "nc_ns", "nps_ns", "ncs_ns",
    "cpsf_ns", "ncsf_ns", "npsfl_ns", "ncsfl_ns", "npciting_ns",
    "cprat_ns", "np_cited_ns", "rank_subfield_ns",
]


@dataclass(frozen=True)
class TableSpec:
    pkey: str | None = None
    time_col: str | None = None
    fkeys: dict[str, str] = field(default_factory=dict)
    drop_columns: list[str] = field(default_factory=list)
    stypes: dict[str, str] = field(default_factory=dict)


TABLES: dict[str, TableSpec] = {
    "career_metrics": TableSpec(
        pkey="metric_id",
        time_col="observation_date",
        fkeys={
            "author_id": "authors",
            "edition_id": "editions",
            "institution_id": "institutions",
            "field_id": "fields",
            "subfield_1_id": "subfields",
            "subfield_2_id": "subfields",
            "country_code": "countries",
        },
        drop_columns=list(NS_COLUMNS),
        stypes={
            "rank": "numerical",
            "c": "numerical",
            "h": "numerical",
            "hm": "numerical",
            "nc": "numerical",
            "np": "numerical",
            "nps": "numerical",
            "ncs": "numerical",
            "cpsf": "numerical",
            "ncsf": "numerical",
            "npsfl": "numerical",
            "ncsfl": "numerical",
            "npciting": "numerical",
            "cprat": "numerical",
            "np_cited": "numerical",
            "self_pct": "numerical",
            "firstyr": "numerical",
            "lastyr": "numerical",
            "rank_subfield": "numerical",
            "subfield_count": "numerical",
            "field_frac": "numerical",
            "subfield_1_frac": "numerical",
            "subfield_2_frac": "numerical",
            # The retraction columns. Present only for the 2023 and 2024
            # editions; NULL for all 955,512 earlier rows. nc_rw is the
            # imputation target.
            "np_rw": "numerical",
            "nc_to_rw": "numerical",
            "nc_rw": "numerical",
            "np_d": "numerical",
            "nc_d": "numerical",
            "observation_date": "timestamp",
        },
    ),
    "authors": TableSpec(
        pkey="author_id",
        # The name columns are dropped, for two reasons that point the same
        # way.
        #
        # Cardinality: authfull_display has 429,276 distinct values across
        # 818,667 rows and name_normalized 389,666, so both are close to
        # row-unique. surname has 143,733, far past what a categorical
        # encoder can generalise over. RelBench's own guidance is to discard
        # columns whose cardinality makes generalisation infeasible, and
        # an author's actual signal comes from the career rows attached to
        # them, not from the spelling of their name.
        #
        # Fairness: embedding names would let the model pick up name origin
        # as a proxy. On a dataset that ranks scientists, that is a hazard
        # worth refusing rather than measuring afterwards.
        #
        # Dropping them also means the graph needs no text embedder at all,
        # which is why sentence-transformers is not a dependency.
        drop_columns=["authfull_display", "name_normalized", "surname"],
        stypes={
            "first_initial": "categorical",
            "firstyr": "numerical",
            "collision_group_size": "numerical",
            "is_ambiguous": "categorical",
            "first_data_year": "numerical",
            "last_data_year": "numerical",
        },
    ),
    "institutions": TableSpec(
        pkey="institution_id",
        fkeys={"country_code": "countries"},
        # inst_name has 66,079 distinct values across 66,079 rows: exactly
        # one per institution, so it is an identifier spelled as words. The
        # institution is already a node with an ID and a country, which is
        # the structure the model can use.
        drop_columns=["inst_name"],
        stypes={"country_code": "categorical"},
    ),
    "editions": TableSpec(
        pkey="edition_id",
        time_col="observation_date",
        # One distinct value per row: provenance for humans, pure noise to a
        # model. columns_present is a packed string of the edition's schema,
        # which is metadata about the table rather than data in it.
        drop_columns=["sha256", "source_filename", "columns_present"],
        stypes={
            "mendeley_version": "numerical",
            "data_year": "numerical",
            "kind": "categorical",
            "observation_date": "timestamp",
            "published_date": "timestamp",
        },
    ),
    "countries": TableSpec(
        pkey="country_code",
        stypes={"name": "categorical"},
    ),
    "fields": TableSpec(
        pkey="field_id",
        stypes={"name": "categorical"},
    ),
    "subfields": TableSpec(
        pkey="subfield_id",
        # The published taxonomy nests subfields under fields. Without this
        # edge the subfield dimension dangles off the taxonomy it belongs to.
        fkeys={"field_id": "fields"},
        stypes={"name": "categorical"},
    ),
}
